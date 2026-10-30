"""Line-shaft downhole pump on the retained TNO ESP polynomial basis."""

from gemini import ops
from gemini.errors import PhysicsRangeError
from gemini.modules.module import Module
from gemini.physics import constants, energy, pumps
from gemini.types import (
    Control,
    Count,
    Dimensionless,
    Efficiency,
    Electricity,
    Frequency,
    Inlet,
    Length,
    LinearPower,
    Outlet,
    Output,
    Parameter,
    Power,
    PressureDifference,
    Stream,
    VolumeFlow,
)


class LineShaftPump(Module):
    """Downhole multistage pump driven by a surface motor through a line shaft.

    The pump stages use the same TNO R11363 polynomial basis as ``ESP``
    (``gemini.physics.pumps``): ``head_coefficients`` and ``power_coefficients`` give ft of head and
    bhp per stage at 60 Hz with the flow in bbl/day, scaled by ``stage_count`` and by the square
    (head) and cube (power) of ``frequency / 60 Hz``. The line shaft from the surface motor to
    the pump at ``setting_depth`` adds the mechanical friction loss
    ``P_friction = shaft_friction_loss * setting_depth * frequency / 60 Hz``: the friction loss
    per shaft length is given at the 60 Hz catalogue speed and grows in proportion to speed
    (constant bearing friction torque), the form of the vertical-turbine-pump manufacturer
    tables of line-shaft friction (horsepower per 100 ft of shaft at a given speed; see
    ANSI/HI 2.3, Rotodynamic Vertical Pumps for Design and Application). Electricity is
    ``(P_pump + P_friction) / motor_efficiency``.

    NOTE(refactor): like ``ESP`` the pump is isothermal: the empirical polynomials do not
    guarantee ``P_pump >= Q H`` (the retained ESP efficiency can exceed one), so no pump or
    shaft loss is allocated to the fluid and no motor loss is reported as ``heat_loss``. The
    electricity is listed as unresolved pump power by ``energy_balance``. Thrust-bearing
    losses, shaft stretch and the column pipe friction (part of the well model) are not
    modelled. Reverse flow, a negative head or a negative pump power (running off the
    polynomial curve) raise ``PhysicsRangeError``; at zero flow the pump runs at shutoff.
    """

    repr_fields = ("stage_count", "setting_depth", "motor_efficiency")

    def __init__(self):
        """Declare line-shaft pump design data, ports and computed performance."""
        super().__init__()

        # Parameters
        self.stage_count = Parameter(Count)
        self.head_coefficients = Parameter(
            list[float], shape=(pumps.POLYNOMIAL_COEFFICIENT_COUNT,), calibratable=True
        )
        self.power_coefficients = Parameter(
            list[float], shape=(pumps.POLYNOMIAL_COEFFICIENT_COUNT,), calibratable=True
        )
        self.setting_depth = Parameter(Length)
        self.shaft_friction_loss = Parameter(LinearPower, ge=0)
        self.motor_efficiency = Parameter(Efficiency)

        # Inlets
        self.suction = Inlet(Stream, stream="brine")

        # Controls
        self.frequency = Control(Frequency)

        # Outputs
        self.flow = Output(VolumeFlow)
        self.head = Output(PressureDifference, soft_sensor=True)
        self.pump_power = Output(Power)
        self.shaft_friction_power = Output(Power)
        self.shaft_power = Output(Power, soft_sensor=True)
        self.efficiency = Output(Dimensionless)
        self.electricity = Output(Electricity)

        # Outlets
        self.discharge = Outlet(Stream, stream="brine")

    def forward(self, inlets):
        """Raise the suction pressure by the pump-curve head."""

        # Outlets
        suction = inlets.suction
        head = self._head(suction.volumetric_flow())

        discharge = suction.with_(p=suction.p + head)

        outlets = dict(discharge=discharge)
        return outlets

    def _compute_outputs(self, inlets, outlets):
        flow = inlets.suction.volumetric_flow()
        pump_power = pumps.power(flow, self.frequency, self.stage_count, self.power_coefficients)
        ops.check(
            pump_power >= 0,
            PhysicsRangeError,
            "{path}: pump power = {pump_power} W at flow = {flow} m3/s; expected >= 0 "
            "(pump off its power curve)",
            path=self.path,
            pump_power=pump_power,
            flow=flow,
        )
        speed = pumps.speed_ratio(self.frequency, constants.ESP_REFERENCE_FREQUENCY)
        friction = pumps.line_shaft_friction_power(
            self.shaft_friction_loss, self.setting_depth, speed
        )
        self.flow = flow
        self.head = outlets.discharge.p - inlets.suction.p
        self.pump_power = pump_power
        self.shaft_friction_power = friction
        self.shaft_power = pump_power + friction
        self.efficiency = pumps.pump_efficiency(flow, self.head, pump_power)
        self.electricity = energy.input_power(self.shaft_power, self.motor_efficiency)

    def _head(self, flow):
        """Return the pump-curve pressure rise [Pa] at a suction volume flow [m3/s]."""
        ops.check(
            flow >= 0,
            PhysicsRangeError,
            "{path}: suction volume flow = {flow} m3/s; reverse flow is unsupported",
            path=self.path,
            flow=flow,
        )
        head = pumps.head(flow, self.frequency, self.stage_count, self.head_coefficients)
        ops.check(
            head >= 0,
            PhysicsRangeError,
            "{path}: head = {head} Pa at flow = {flow} m3/s; expected >= 0 (pump off "
            "its head curve)",
            path=self.path,
            head=head,
            flow=flow,
        )
        return head
