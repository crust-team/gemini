"""Silica-gel/water adsorption chiller driven by low-temperature hot water."""

from gemini.core.modules.module import Module
from gemini.core.physics import refrigeration
from gemini.core.types import (
    Control,
    Dimensionless,
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
from gemini.errors import ConfigurationError, PhysicsRangeError


class AdsorptionChiller(Module):
    """Silica-gel/water adsorption chiller driven by hot water of 55 to 90 degC.

    Three circuits as in ``AbsorptionUnit``: ``generator_in`` carries the driving hot water that
    desorbs the bed, ``chilled_in`` the evaporator water and ``cooling_in`` the cooling water of
    the adsorbing bed and the condenser. The machine is a chiller only: ``temperature_setpoint``
    is the chilled outlet temperature and ``capacity`` caps the evaporator duty.

    Adsorption chillers run in batch cycles (two or more beds switching between adsorption and
    desorption); the model represents cycle-averaged duties over a step much longer than the
    cycle (minutes), so it suits 15-minute or hourly steps. Its characteristic map is the
    characteristic equation of the sorption machine, Q_E = s * (ddt - ddt_min) with
    ddt = t_G - a * t_AC + r * t_E at the mean circuit temperatures in degC, solved in closed form
    from the inlet temperatures (``refrigeration.sorption_evaporator_capacity``); its own
    coefficients are fitted to the adsorption machine. The delivered evaporator duty is the
    smallest of that, the setpoint request and the capacity. Q_G = Q_E / thermal_cop,
    electricity (pumps, valves and controls) is auxiliary_power_ratio * Q_E and
    Q_AC = Q_G + Q_E + electricity, so the model is first-law closed.
    ``is_capped`` is true whenever the delivered duty falls short of the setpoint request,
    whether capacity, the characteristic equation or the driving temperature limits it.

    Assumptions: constant cycle-averaged thermal COP, 0.55 by default: Wang and Oliveira (2006),
    "Adsorption refrigeration - an efficient way to make good use of waste heat and solar
    energy", Progress in Energy and Combustion Science 32, 424-458, report about 0.5 to 0.6 for
    commercial silica-gel/water chillers. No pressure loss, casing heat loss or cycle dynamics;
    constant liquid heat capacity per stream. Validity: driving hot water from
    ``minimum_driving_temperature`` (55 degC; below it the chiller is off) to
    ``maximum_driving_temperature`` (90 degC; above it the map is not valid and the call raises
    ``PhysicsRangeError``), cooling water of 20 to 35 degC, chilled water above 5 degC, circuit
    flows near the rated flows of the fit.
    """

    def __init__(self):
        """Declare adsorption chiller design data, its three circuits and performance."""
        super().__init__()

        # Parameters
        self.capacity = Parameter(Power, gt=0)
        self.characteristic_slope = Parameter(ThermalConductance, gt=0)
        self.minimum_driving_difference = Parameter(TemperatureDifference)
        self.rejection_coefficient = Parameter(Dimensionless)
        self.evaporator_coefficient = Parameter(Dimensionless)
        self.thermal_cop = Parameter(Ratio, default=0.55, gt=0)
        self.auxiliary_power_ratio = Parameter(Ratio)
        self.minimum_driving_temperature = Parameter(Temperature, default=328.15)
        self.maximum_driving_temperature = Parameter(Temperature, default=363.15)

        # Inlets
        self.generator_in = Inlet(Stream)
        self.chilled_in = Inlet(Stream)
        self.cooling_in = Inlet(Stream)

        # Controls
        self.temperature_setpoint = Control(Temperature)

        # Outputs
        self.cop = Output(Ratio | None)
        self.generator_duty = Output(Power)
        self.evaporator_duty = Output(Power)
        self.adsorber_condenser_duty = Output(Power)
        self.electricity = Output(Power)
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
        requested = rates["chilled_in"] * max(0, chilled_in.T - self.temperature_setpoint)
        evaporator = min(requested, self._available_duty(inlets, rates), self.capacity)
        generator = evaporator / self.thermal_cop
        electricity = evaporator * self.auxiliary_power_ratio
        rejection = generator + evaporator + electricity
        return {
            "cop": evaporator / generator if evaporator else None,
            "generator_duty": generator,
            "evaporator_duty": evaporator,
            "adsorber_condenser_duty": rejection,
            "electricity": electricity,
            "is_capped": evaporator < requested,
            "generator_out_T": _outlet_T(generator_in, rates["generator_in"], -generator),
            "chilled_out_T": _outlet_T(chilled_in, rates["chilled_in"], -evaporator),
            "cooling_out_T": _outlet_T(cooling_in, rates["cooling_in"], rejection),
        }

    def _available_duty(self, inlets, rates):
        """Return the evaporator duty [W] the characteristic map allows at these inlets."""
        driving_T = inlets.generator_in.T
        if self.minimum_driving_temperature >= self.maximum_driving_temperature:
            raise ConfigurationError(
                f"{self.path}: minimum_driving_temperature = "
                f"{self.minimum_driving_temperature} K; expected below "
                f"maximum_driving_temperature = {self.maximum_driving_temperature} K"
            )
        if driving_T > self.maximum_driving_temperature:
            raise PhysicsRangeError(
                f"{self.path}: generator_in.T = {driving_T} K; expected at most "
                f"maximum_driving_temperature = {self.maximum_driving_temperature} K"
            )
        if driving_T < self.minimum_driving_temperature:
            return 0.0
        return refrigeration.sorption_evaporator_capacity(
            driving_T,
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
