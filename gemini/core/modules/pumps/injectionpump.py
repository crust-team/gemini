"""Injection pump using supplied curves or a discharge-pressure setpoint."""

from pydantic import BaseModel, ConfigDict, Field, model_validator

from gemini.core.modules.module import Module
from gemini.core.physics import pumps
from gemini.core.types.quantities import (
    Count,
    Efficiency,
    Frequency,
    Power,
    Pressure,
    PressureDifference,
)
from gemini.core.types.results import ModuleResult


class InjectionPump(Module):
    """Raise brine pressure with a simple hydraulic-power estimate."""

    name = "injectionpump"
    category = "pumps"
    description = "Injection pump using curves or a pressure setpoint and efficiency."
    fidelity = "simple"
    inlets = ("suction",)
    outlets = ("discharge",)
    soft_sensors = ("head", "power", "discharge_pressure")
    calibratable = ("efficiency",)

    class Params(BaseModel):
        """Optional pump curves and fallback hydraulic efficiency."""

        model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
        no_stages: Count | None = Field(None, gt=0, description="Number of stages [-]")
        pump_type: str = Field("unspecified", description="Pump type [-]")
        efficiency: Efficiency = Field(0.7, gt=0, le=1, description="Hydraulic efficiency [-]")
        head_coeff: list[float] | None = Field(
            None, min_length=6, max_length=6, description="US head polynomial [US basis]"
        )
        power_coeff: list[float] | None = Field(
            None, min_length=6, max_length=6, description="US power polynomial [US basis]"
        )

        @model_validator(mode="after")
        def curve_stages(self):
            """Require stage count when a head curve is supplied."""
            if self.head_coeff is not None and self.no_stages is None:
                raise ValueError("injectionpump: curves require no_stages")
            return self

    class Inputs(BaseModel):
        """Discharge target or drive frequency for supplied curves."""

        model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
        discharge_pressure: Pressure | None = Field(
            None, ge=0, description="Discharge setpoint [Pa]"
        )
        frequency: Frequency = Field(60, gt=0, description="Drive frequency [Hz]")

    class Outputs(BaseModel):
        """Hydraulic rise and predicted power consumption."""

        head: PressureDifference = Field(..., ge=0, description="Pressure rise [Pa]")
        power: Power = Field(..., ge=0, description="Power draw [W]")
        discharge_pressure: Pressure = Field(..., ge=0, description="Discharge pressure [Pa]")

    def forward(self, inputs, streams_in):
        """Evaluate supplied curves or Q times pressure rise divided by efficiency."""
        stream = streams_in["suction"]
        flow = stream.volumetric_flow()
        if flow < 0:
            raise ValueError(f"{self.path}: reverse flow is unsupported")
        if self.params.head_coeff is not None:
            head = pumps.head(flow, inputs.frequency, self.params.no_stages, self.params.head_coeff)
        elif inputs.discharge_pressure is not None:
            head = inputs.discharge_pressure - stream.p
        else:
            raise ValueError(f"{self.path}: supply discharge_pressure or pump curves")
        if head < 0:
            raise ValueError(f"{self.path}: discharge pressure is below suction pressure")
        power = flow * head / self.params.efficiency
        if self.params.head_coeff is not None and self.params.power_coeff is not None:
            power = pumps.power(
                flow, inputs.frequency, self.params.no_stages, self.params.power_coeff
            )
        outlet = stream.with_(p=stream.p + head)
        return ModuleResult(
            self.Outputs(head=head, power=power, discharge_pressure=outlet.p), {"discharge": outlet}
        )
