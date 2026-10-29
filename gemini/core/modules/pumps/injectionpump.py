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
from gemini.errors import ConfigurationError, PhysicsRangeError


class InjectionPump(Module):
    """Raise brine pressure with a simple hydraulic-power estimate."""

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

    def forward(self, inlets):
        """Raise pressure from a supplied curve or discharge-pressure setpoint."""

        # Outlets
        suction = inlets.suction
        head = self._head(suction)
        if head < 0:
            raise PhysicsRangeError(
                f"{self.path}: head = {head} Pa; discharge pressure is below suction pressure"
            )

        discharge = suction.with_(p=suction.p + head)

        outlets = dict(discharge=discharge)
        return outlets

    def _compute_outputs(self, inlets, outlets):
        suction = inlets.suction
        discharge = outlets.discharge
        flow = suction.volumetric_flow()
        self.head = discharge.p - suction.p
        if self.head_coeff is not None and self.power_coeff is not None:
            self.power = pumps.power(flow, self.frequency, self.no_stages, self.power_coeff)
        else:
            self.power = flow * self.head / self.efficiency
        self.discharge_pressure = discharge.p
        self.electricity = self.power

    def _head(self, suction):
        """Return the pressure rise [Pa] from the head curve, else from the pressure setpoint.

        A ``power_coeff`` curve is used for power only together with a ``head_coeff`` curve.
        """
        flow = suction.volumetric_flow()
        if flow < 0:
            raise PhysicsRangeError(
                f"{self.path}: suction volume flow = {flow} m3/s; reverse flow is unsupported"
            )
        if self.head_coeff is not None:
            if self.no_stages is None:
                raise ConfigurationError(f"{self.path}: head_coeff curves require no_stages")
            return pumps.head(flow, self.frequency, self.no_stages, self.head_coeff)
        if self.pressure_setpoint is not None:
            return self.pressure_setpoint - suction.p
        raise ConfigurationError(
            f"{self.path}: supply the pressure_setpoint control or head_coeff and no_stages"
        )
