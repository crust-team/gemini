"""Injection pump using supplied curves or a discharge-pressure setpoint."""

from gemini import ops
from gemini.errors import PhysicsError, ValidationError
from gemini.modules.module import Module
from gemini.modules.pumps import _physics
from gemini.physics import energy, pumps
from gemini.types import (
    Control,
    Count,
    Efficiency,
    Electricity,
    Frequency,
    Inlet,
    Outlet,
    Output,
    Parameter,
    Power,
    Pressure,
    PressureDifference,
    Stream,
)


class InjectionPump(Module):
    """Raise brine pressure with a simple hydraulic-power estimate."""

    repr_fields = ("stage_count", "efficiency", "pump_type")

    def __init__(self):
        """Declare injection pump design data, ports and controls."""
        super().__init__()

        # Parameters
        self.stage_count = Parameter(Count | None, default=None)
        self.pump_type = Parameter(str, default="unspecified")
        self.efficiency = Parameter(
            Efficiency, default=pumps.DEFAULT_INJECTION_PUMP_EFFICIENCY, calibratable=True
        )
        self.head_coefficients = Parameter(
            list[float] | None, default=None, shape=(pumps.POLYNOMIAL_COEFFICIENT_COUNT,)
        )
        self.power_coefficients = Parameter(
            list[float] | None, default=None, shape=(pumps.POLYNOMIAL_COEFFICIENT_COUNT,)
        )

        # Inlets
        self.suction = Inlet(Stream, stream="brine")

        # Controls
        self.pressure_setpoint = Control(Pressure | None, default=None)
        self.frequency = Control(Frequency, default=pumps.DEFAULT_INJECTION_PUMP_FREQUENCY)

        # Outputs
        self.head = Output(PressureDifference, soft_sensor=True)
        self.power = Output(Power, soft_sensor=True)
        self.discharge_pressure = Output(Pressure, soft_sensor=True)
        self.electricity = Output(Electricity)

        # Outlets
        self.discharge = Outlet(Stream, stream="brine")

    def forward(self, inlets):
        """Raise pressure from a supplied curve or discharge-pressure setpoint."""

        # Outlets
        suction = inlets.suction
        head = self._head(suction)
        ops.check(
            head >= 0,
            PhysicsError,
            "{path}: head = {head} Pa; discharge pressure is below suction pressure",
            path=self.path,
            head=head,
        )

        discharge = suction.with_(p=suction.p + head)

        outlets = dict(discharge=discharge)
        return outlets

    def _compute_outputs(self, inlets, outlets):
        suction = inlets.suction
        discharge = outlets.discharge
        flow = suction.volumetric_flow()
        self.head = discharge.p - suction.p
        if self.head_coefficients is not None and self.power_coefficients is not None:
            self.power = pumps.power(
                flow, self.frequency, self.stage_count, self.power_coefficients
            )
        else:
            self.power = energy.input_power(pumps.hydraulic_power(flow, self.head), self.efficiency)
        self.discharge_pressure = discharge.p
        self.electricity = self.power

    def _head(self, suction):
        """Return the pressure rise [Pa] from the head curve, else from the pressure setpoint.

        A ``power_coefficients`` curve is used for power only together with a ``head_coefficients``
        curve.
        """
        flow = suction.volumetric_flow()
        ops.check(
            flow >= 0,
            PhysicsError,
            "{path}: suction volume flow = {flow} m3/s; reverse flow is unsupported",
            path=self.path,
            flow=flow,
        )
        if self.head_coefficients is not None:
            if self.stage_count is None:
                raise ValidationError(
                    f"{self.path}: head_coefficients curves require stage_count",
                    code="invalid_design",
                )
            return _physics.head(flow, self.frequency, self.stage_count, self.head_coefficients)
        if self.pressure_setpoint is not None:
            return self.pressure_setpoint - suction.p
        raise ValidationError(
            f"{self.path}: supply the pressure_setpoint control or head_coefficients and "
            "stage_count",
            code="invalid_design",
        )
