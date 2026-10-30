"""Single-effect water/LiBr absorption chiller or heat pump driven by hot water."""

from typing import Literal

from gemini.core.modules.module import Module
from gemini.core.physics import refrigeration
from gemini.core.types import (
    Control,
    Dimensionless,
    Electricity,
    Inlet,
    Outlet,
    Output,
    Parameter,
    Power,
    Ratio,
    Stream,
    Temperature,
    TemperatureDifference,
    ThermalConductance,
)
from gemini.errors import PhysicsRangeError


class AbsorptionUnit(Module):
    """Single-effect water/LiBr absorption chiller or heat pump driven by hot water.

    Three circuits: ``generator_in`` carries the driving hot water (the geothermal heat),
    ``chilled_in`` the evaporator water and ``cooling_in`` the cooling water of absorber and
    condenser. In ``chiller`` mode the useful duty is the evaporator duty and
    ``temperature_setpoint`` is the chilled outlet temperature; in ``heat_pump`` mode
    (absorption heat pump type I) the useful duty is the absorber plus condenser heat and the
    setpoint is the cooling-circuit outlet temperature. ``capacity`` caps the useful duty.

    The available evaporator duty follows the characteristic equation (Hellmann, Schweigler and
    Ziegler 1999; Kuehn and Ziegler 2005) Q_E = s * (ddt - ddt_min) with
    ddt = t_G - a * t_AC + r * t_E at the arithmetic mean circuit temperatures in degC, solved
    in closed form from the inlet temperatures
    (``refrigeration.sorption_evaporator_capacity``). The delivered evaporator duty is the
    smallest of that, the setpoint request and the capacity. Q_G = Q_E / thermal_cop, the
    solution pump electricity is auxiliary_power_ratio * Q_E and Q_AC = Q_G + Q_E +
    electricity, so the model is first-law closed. Below ``minimum_driving_temperature`` at the
    generator inlet the unit is off.
    ``is_capped`` is true whenever the delivered duty falls short of the setpoint request,
    whether capacity, the characteristic equation or the driving temperature limits it.

    Assumptions: constant thermal COP (Herold, Radermacher and Klein 2016, Absorption Chillers
    and Heat Pumps, 2nd ed., give about 0.7 for single-effect water/LiBr machines, the default),
    no pressure loss, no casing heat loss, constant liquid heat capacity per stream; the unit
    throttles to the request without changing its COP. Validity: the characteristic
    coefficients ``characteristic_slope``, ``minimum_driving_difference``,
    ``rejection_coefficient`` (a) and ``evaporator_coefficient`` (r) are fitted to one machine at
    near-rated circuit flows (ideal Duehring form a = 1 + B, r = B with B about 1.1 to 1.2);
    driving hot water of about 70 to 120 degC, cooling water of 20 to 40 degC and chilled water
    above 4 degC. Crystallisation limits are not modelled.
    """

    def __init__(self):
        """Declare absorption machine design data, its three circuits and performance."""
        super().__init__()

        # Parameters
        self.mode = Parameter(Literal["chiller", "heat_pump"])
        self.capacity = Parameter(Power, gt=0)
        self.characteristic_slope = Parameter(ThermalConductance, gt=0)
        self.minimum_driving_difference = Parameter(TemperatureDifference)
        self.rejection_coefficient = Parameter(Dimensionless)
        self.evaporator_coefficient = Parameter(Dimensionless)
        self.thermal_cop = Parameter(Ratio, default=0.7, gt=0)
        self.auxiliary_power_ratio = Parameter(Ratio)
        self.minimum_driving_temperature = Parameter(Temperature, default=353.15)

        # Inlets
        self.generator_in = Inlet(Stream)
        self.chilled_in = Inlet(Stream)
        self.cooling_in = Inlet(Stream)

        # Controls
        self.temperature_setpoint = Control(Temperature)

        # Outputs
        self.cop = Output(Ratio | None)
        self.useful_duty = Output(Power)
        self.generator_duty = Output(Power)
        self.evaporator_duty = Output(Power)
        self.absorber_condenser_duty = Output(Power)
        self.electricity = Output(Electricity)
        self.driving_temperature_difference = Output(TemperatureDifference)
        self.is_capped = Output(bool)
        self.generator_out_T = Output(Temperature)
        self.chilled_out_T = Output(Temperature)
        self.cooling_out_T = Output(Temperature)

        # Outlets
        self.generator_out = Outlet(Stream)
        self.chilled_out = Outlet(Stream)
        self.cooling_out = Outlet(Stream)

    def forward(self, inlets):
        """Cool the generator and chilled circuits and heat the cooling circuit."""

        # Outlets
        values = self._performance(inlets)
        generator_out = inlets.generator_in.with_(T=values["generator_out_T"])
        chilled_out = inlets.chilled_in.with_(T=values["chilled_out_T"])
        cooling_out = inlets.cooling_in.with_(T=values["cooling_out_T"])

        outlets = dict(
            generator_out=generator_out, chilled_out=chilled_out, cooling_out=cooling_out
        )
        return outlets

    def _compute_outputs(self, inlets, outlets):
        for name, value in self._performance(inlets).items():
            setattr(self, name, value)
        self.driving_temperature_difference = refrigeration.characteristic_temperature_difference(
            (inlets.generator_in.T + outlets.generator_out.T) / 2,
            (inlets.cooling_in.T + outlets.cooling_out.T) / 2,
            (inlets.chilled_in.T + outlets.chilled_out.T) / 2,
            self.rejection_coefficient,
            self.evaporator_coefficient,
        )

    def _performance(self, inlets):
        """Return the duties [W], COP and outlet temperatures [K] of one operating point."""
        generator_in, chilled_in, cooling_in = (
            inlets.generator_in,
            inlets.chilled_in,
            inlets.cooling_in,
        )
        rates = _rates(self.path, inlets)
        rejection_ratio = 1 + 1 / self.thermal_cop + self.auxiliary_power_ratio
        if self.mode == "chiller":
            useful_ratio = 1.0
            requested = rates["chilled_in"] * max(0, chilled_in.T - self.temperature_setpoint)
        else:
            useful_ratio = rejection_ratio
            requested = rates["cooling_in"] * max(0, self.temperature_setpoint - cooling_in.T)
        evaporator = min(
            requested / useful_ratio,
            self._available_duty(inlets, rates),
            self.capacity / useful_ratio,
        )
        generator = evaporator / self.thermal_cop
        electricity = evaporator * self.auxiliary_power_ratio
        rejection = generator + evaporator + electricity
        useful = evaporator if self.mode == "chiller" else rejection
        return {
            "cop": useful / generator if evaporator else None,
            "useful_duty": useful,
            "generator_duty": generator,
            "evaporator_duty": evaporator,
            "absorber_condenser_duty": rejection,
            "electricity": electricity,
            "is_capped": evaporator < requested / useful_ratio,
            "generator_out_T": _outlet_T(generator_in, rates["generator_in"], -generator),
            "chilled_out_T": _outlet_T(chilled_in, rates["chilled_in"], -evaporator),
            "cooling_out_T": _outlet_T(cooling_in, rates["cooling_in"], rejection),
        }

    def _available_duty(self, inlets, rates):
        """Return the evaporator duty [W] the characteristic equation allows at these inlets."""
        if inlets.generator_in.T < self.minimum_driving_temperature:
            return 0.0
        return refrigeration.sorption_evaporator_capacity(
            inlets.generator_in.T,
            inlets.cooling_in.T,
            inlets.chilled_in.T,
            rates["generator_in"],
            rates["cooling_in"],
            rates["chilled_in"],
            slope=self.characteristic_slope,
            minimum_driving_difference=self.minimum_driving_difference,
            rejection_coefficient=self.rejection_coefficient,
            evaporator_coefficient=self.evaporator_coefficient,
            thermal_cop=self.thermal_cop,
            auxiliary_power_ratio=self.auxiliary_power_ratio,
        )


def _rates(path, inlets):
    """Return each inlet's heat capacity rate m_dot * cp [W/K]; reject negative flow."""
    rates = {}
    for port, stream in inlets.items():
        if stream.m_dot < 0:
            raise PhysicsRangeError(f"{path}: {port}.m_dot = {stream.m_dot} kg/s; expected >= 0")
        rates[port] = stream.m_dot * stream.fluid.properties(stream.p, stream.T).cp_l
    return rates


def _outlet_T(stream, rate, duty):
    """Return the outlet temperature [K] after adding ``duty`` [W] at capacity rate ``rate``."""
    return stream.T + duty / rate if duty else stream.T
