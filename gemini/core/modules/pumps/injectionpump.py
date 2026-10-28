"""Injection pump using supplied curves or a discharge-pressure setpoint."""

from gemini.core.modules.module import Module
from gemini.core.physics import pumps
from gemini.core.types import (
    Control,
    Count,
    Efficiency,
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

    fidelity = "simple"
    repr_fields = ("no_stages", "efficiency", "pump_type")

    def __init__(self):
        """Declare injection pump design data, ports and controls."""
        super().__init__()

        # Parameters
        self.no_stages = Parameter(Count | None, default=None)
        self.pump_type = Parameter(str, default="unspecified")
        self.efficiency = Parameter(Efficiency, default=0.7, calibratable=True)
        self.head_coeff = Parameter(list[float] | None, default=None, shape=(6,))
        self.power_coeff = Parameter(list[float] | None, default=None, shape=(6,))

        # Inlets
        self.suction = Inlet(Stream)

        # Controls
        self.pressure_setpoint = Control(Pressure | None, default=None)
        self.frequency = Control(Frequency, default=60)

        # Outputs
        self.head = Output(PressureDifference, soft_sensor=True)
        self.power = Output(Power, soft_sensor=True)
        self.discharge_pressure = Output(Pressure, soft_sensor=True)
        self.electricity = Output(Power)

        # Outlets
        self.discharge = Outlet(Stream)

    def forward(self, suction):
        """Evaluate supplied curves or Q times pressure rise divided by efficiency."""

        flow = suction.volumetric_flow()
        if flow < 0:
            raise ValueError(f"{self.path}: reverse flow is unsupported")
        if self.head_coeff is not None:
            if self.no_stages is None:
                raise ValueError(f"{self.path}: curves require no_stages")
            head = pumps.head(flow, self.frequency, self.no_stages, self.head_coeff)
        elif self.pressure_setpoint is not None:
            head = self.pressure_setpoint - suction.p
        else:
            raise ValueError(f"{self.path}: supply discharge_pressure or pump curves")
        if head < 0:
            raise ValueError(f"{self.path}: discharge pressure is below suction pressure")

        # Outlets
        discharge = suction.with_(p=suction.p + head)

        outlets = dict(discharge=discharge)
        return outlets

    def _compute_outputs(self, suction, discharge):
        flow = suction.volumetric_flow()
        self.head = discharge.p - suction.p
        self.power = flow * self.head / self.efficiency
        if self.head_coeff is not None and self.power_coeff is not None:
            self.power = pumps.power(flow, self.frequency, self.no_stages, self.power_coeff)
        self.discharge_pressure = discharge.p
        self.electricity = self.power
