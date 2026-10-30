"""Single-effect water/LiBr absorption chiller or heat pump driven by hot water."""

from typing import Literal

from gemini import ops
from gemini.core.modules.heat import _sorption as sorption
from gemini.core.modules.module import Module
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
        generator_out, chilled_out, cooling_out = sorption.outlet_streams(
            inlets, self._performance(inlets)
        )

        outlets = dict(
            generator_out=generator_out, chilled_out=chilled_out, cooling_out=cooling_out
        )
        return outlets

    def _compute_outputs(self, inlets, outlets):
        sorption.assign_outputs(self, inlets, outlets, self._performance(inlets))

    def _performance(self, inlets):
        """Return the duties [W], COP and outlet temperatures [K] of one operating point."""
        generator_in, chilled_in, cooling_in = (
            inlets.generator_in,
            inlets.chilled_in,
            inlets.cooling_in,
        )
        rates = sorption.rates(self.path, inlets)
        rejection_ratio = 1 + 1 / self.thermal_cop + self.auxiliary_power_ratio
        if self.mode == "chiller":
            useful_ratio = 1.0
            requested = rates["chilled_in"] * ops.maximum(
                0, chilled_in.T - self.temperature_setpoint
            )
        else:
            useful_ratio = rejection_ratio
            requested = rates["cooling_in"] * ops.maximum(
                0, self.temperature_setpoint - cooling_in.T
            )
        evaporator = ops.minimum(
            ops.minimum(requested / useful_ratio, self._available_duty(inlets, rates)),
            self.capacity / useful_ratio,
        )
        generator = evaporator / self.thermal_cop
        electricity = evaporator * self.auxiliary_power_ratio
        rejection = generator + evaporator + electricity
        useful = evaporator if self.mode == "chiller" else rejection
        return {
            "cop": ops.where(evaporator != 0, useful / generator, None),
            "useful_duty": useful,
            "generator_duty": generator,
            "evaporator_duty": evaporator,
            "absorber_condenser_duty": rejection,
            "electricity": electricity,
            "is_capped": evaporator < requested / useful_ratio,
            "generator_out_T": sorption.outlet_T(generator_in, rates["generator_in"], -generator),
            "chilled_out_T": sorption.outlet_T(chilled_in, rates["chilled_in"], -evaporator),
            "cooling_out_T": sorption.outlet_T(cooling_in, rates["cooling_in"], rejection),
        }

    def _available_duty(self, inlets, rates):
        """Return the evaporator duty [W] the characteristic equation allows at these inlets."""
        capacity = sorption.evaporator_capacity(self, inlets, rates)
        return ops.where(inlets.generator_in.T < self.minimum_driving_temperature, 0.0, capacity)
