"""Dry or wet (evaporative) closed-circuit cooler rejecting heat to ambient air."""

from typing import Literal

from gemini import ops
from gemini.errors import PhysicsError, ValidationError
from gemini.modules.module import Module
from gemini.physics import heat_transfer, psychrometrics
from gemini.types import (
    Boundary,
    Control,
    Duty,
    Electricity,
    HeatLoss,
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


class Cooler(Module):
    """Dry or wet (evaporative) closed-circuit cooler rejecting heat to ambient air.

    The fluid is cooled towards ``temperature_setpoint`` but not below the reference air
    temperature plus ``approach``: the dry-bulb ``ambient_temperature`` for a ``dry`` cooler and
    the ``wet_bulb_temperature`` for a ``wet`` one (a ``wet`` cooler without a wet-bulb
    temperature raises ``ValidationError``). The removed duty is capped at ``capacity``.
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
        self.latent_heat = Parameter(
            SpecificEnthalpy, default=psychrometrics.DEFAULT_LATENT_HEAT, gt=0
        )

        # Inlets
        self.inlet = Inlet(Stream, stream="hot_water")

        # Controls
        self.temperature_setpoint = Control(Temperature)

        # Boundaries
        self.ambient_temperature = Boundary(Temperature)
        self.wet_bulb_temperature = Boundary(Temperature | None, default=None)

        # Outputs
        self.duty = Output(Duty)
        self.outlet_T = Output(Temperature)
        self.electricity = Output(Electricity)
        self.heat_loss = Output(HeatLoss)
        self.evaporation_rate = Output(MassFlow)
        self.is_capped = Output(bool)

        # Outlets
        self.outlet = Outlet(Stream, stream="hot_water")

    def forward(self, inlets):
        """Cool the stream by the rejected duty; its mass flow is unchanged."""

        # Outlets
        inlet = inlets.inlet
        duty, rate, _ = self._duty(inlet)
        outlet = inlet.with_(T=inlet.T - heat_transfer.temperature_change(duty, rate))

        outlets = dict(outlet=outlet)
        return outlets

    def _compute_outputs(self, inlets, outlets):
        duty, _, requested = self._duty(inlets.inlet)
        self.duty = duty
        self.outlet_T = outlets.outlet.T
        self.electricity = heat_transfer.fan_power(duty, self.specific_fan_power)
        self.heat_loss = duty + self.electricity
        self.evaporation_rate = (
            psychrometrics.evaporation_rate(duty, self.latent_heat)
            if self.cooler_type == "wet"
            else 0.0
        )
        self.is_capped = requested > self.capacity

    def _duty(self, inlet):
        """Return the rejected duty [W], heat capacity rate [W/K] and uncapped request [W]."""
        ops.check(
            inlet.m_dot >= 0,
            PhysicsError,
            "{path}: inlet.m_dot = {m_dot} kg/s; expected >= 0",
            path=self.path,
            m_dot=inlet.m_dot,
        )
        target = ops.maximum(self.temperature_setpoint, self._air_temperature() + self.approach)
        rate = inlet.heat_capacity_rate()
        requested = heat_transfer.setpoint_duty(rate, inlet.T - target)
        return ops.minimum(requested, self.capacity), rate, requested

    def _air_temperature(self):
        """Return the reference air temperature [K]: dry bulb for dry, wet bulb for wet."""
        if self.cooler_type == "dry":
            return self.ambient_temperature
        wet_bulb = self.wet_bulb_temperature
        if wet_bulb is None:
            raise ValidationError(
                f"{self.path}: wet_bulb_temperature = None; expected a value for a wet cooler",
                code="invalid_design",
            )
        ops.check(
            wet_bulb <= self.ambient_temperature,
            PhysicsError,
            "{path}: wet_bulb_temperature = {wet_bulb} K; expected at most "
            "ambient_temperature = {ambient} K",
            path=self.path,
            wet_bulb=wet_bulb,
            ambient=self.ambient_temperature,
        )
        return wet_bulb
