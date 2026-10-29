"""Dry or wet (evaporative) closed-circuit cooler rejecting heat to ambient air."""

from typing import Literal

from gemini.core.modules.module import Module
from gemini.core.types import (
    Boundary,
    Control,
    Inlet,
    MassFlow,
    Outlet,
    Output,
    Parameter,
    Power,
    Ratio,
    SpecificEnthalpy,
    Stream,
    Temperature,
    TemperatureDifference,
)
from gemini.errors import ConfigurationError, PhysicsRangeError


class Cooler(Module):
    """Dry or wet (evaporative) closed-circuit cooler rejecting heat to ambient air.

    The fluid is cooled towards ``temperature_setpoint`` but not below the reference air
    temperature plus ``approach``: the dry-bulb ``ambient_temperature`` for a ``dry`` cooler and
    the ``wet_bulb_temperature`` for a ``wet`` one (a ``wet`` cooler without a wet-bulb
    temperature raises ``ConfigurationError``). The removed duty is capped at ``capacity``.
    Fans draw electricity = specific_fan_power * duty; the fan work is dissipated into the air
    stream, so heat_loss = duty + electricity and the model is first-law closed.

    A wet cooler is a closed-circuit evaporative fluid cooler: spray water evaporates on the
    outside of the coil, so the process stream keeps its mass flow and the evaporated water is
    reported as evaporation_rate = duty / latent_heat (default 2430 kJ/kg, water at about
    30 degC from the IAPWS-IF97 saturation tables). Taking all rejected heat as latent gives
    an upper bound (rules of thumb put about 80 to 90 % of the heat into evaporation); make-up
    water also covers drift and blowdown, which are not modelled.

    Assumptions: fixed approach at every load (the outlet limit does not improve at part load),
    fan power proportional to duty (speed-controlled fans, no cubic fan law), no pressure loss,
    constant liquid heat capacity. Validity: ambient air of about -20 to 45 degC; approach
    values of 5 to 15 K are typical for dry coolers and 3 to 8 K for wet coolers (ASHRAE
    Handbook, HVAC Systems and Equipment, chapters on cooling towers and dry coolers).
    """

    def __init__(self):
        """Declare cooler design data, the cooled stream, ambient air and energy flows."""
        super().__init__()

        # Parameters
        self.cooler_type = Parameter(Literal["dry", "wet"])
        self.capacity = Parameter(Power, gt=0)
        self.approach = Parameter(TemperatureDifference, ge=0)
        self.specific_fan_power = Parameter(Ratio)
        self.latent_heat = Parameter(SpecificEnthalpy, default=2.43e6, gt=0)

        # Inlets
        self.inlet = Inlet(Stream)

        # Controls
        self.temperature_setpoint = Control(Temperature)

        # Boundaries
        self.ambient_temperature = Boundary(Temperature)
        self.wet_bulb_temperature = Boundary(Temperature | None, default=None)

        # Outputs
        self.duty = Output(Power)
        self.outlet_T = Output(Temperature)
        self.electricity = Output(Power)
        self.heat_loss = Output(Power)
        self.evaporation_rate = Output(MassFlow)
        self.is_capped = Output(bool)

        # Outlets
        self.outlet = Outlet(Stream)

    def forward(self, inlets):
        """Cool the stream by the rejected duty; its mass flow is unchanged."""

        # Outlets
        inlet = inlets.inlet
        duty, rate, _ = self._duty(inlet)
        outlet = inlet.with_(T=inlet.T - duty / rate if duty else inlet.T)

        outlets = dict(outlet=outlet)
        return outlets

    def _compute_outputs(self, inlets, outlets):
        duty, _, requested = self._duty(inlets.inlet)
        self.duty = duty
        self.outlet_T = outlets.outlet.T
        self.electricity = self.specific_fan_power * duty
        self.heat_loss = duty + self.electricity
        self.evaporation_rate = duty / self.latent_heat if self.cooler_type == "wet" else 0.0
        self.is_capped = requested > self.capacity

    def _duty(self, inlet):
        """Return the rejected duty [W], heat capacity rate [W/K] and uncapped request [W]."""
        if inlet.m_dot < 0:
            raise PhysicsRangeError(f"{self.path}: inlet.m_dot = {inlet.m_dot} kg/s; expected >= 0")
        target = max(self.temperature_setpoint, self._air_temperature() + self.approach)
        rate = inlet.m_dot * inlet.fluid.properties(inlet.p, inlet.T).cp_l
        requested = rate * max(0, inlet.T - target)
        return min(requested, self.capacity), rate, requested

    def _air_temperature(self):
        """Return the reference air temperature [K]: dry bulb for dry, wet bulb for wet."""
        if self.cooler_type == "dry":
            return self.ambient_temperature
        wet_bulb = self.wet_bulb_temperature
        if wet_bulb is None:
            raise ConfigurationError(
                f"{self.path}: wet_bulb_temperature = None; expected a value for a wet cooler"
            )
        if wet_bulb > self.ambient_temperature:
            raise PhysicsRangeError(
                f"{self.path}: wet_bulb_temperature = {wet_bulb} K; expected at most "
                f"ambient_temperature = {self.ambient_temperature} K"
            )
        return wet_bulb
