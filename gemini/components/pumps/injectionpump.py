"""InjectionPump component.

Raises pressure to return cooled brine to the aquifer. The original GEMINI unit had no equipment
model.
"""

from pydantic import BaseModel, ConfigDict, Field

from gemini.core.base.component import Component


class InjectionPump(Component):
    """Raises pressure to return cooled brine to the aquifer."""

    name = "injectionpump"
    category = "pumps"
    description = "Raises pressure to return cooled brine to the aquifer."
    inlets = ("suction",)
    outlets = ("discharge",)

    class Params(BaseModel):
        """Available design parameters; no performance model is assumed."""

        model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
        no_stages: int = Field(..., gt=0, description="Number of pump stages [-]")
        pump_type: str = Field(..., description="Pump type [-]")

    class Inputs(BaseModel):
        """No operating inputs are modelled yet."""

        model_config = ConfigDict(extra="forbid")

    class Outputs(BaseModel):
        """Declared future performance results."""

        head: float = Field(..., description="Pressure rise [Pa]")
        power: float = Field(..., description="Shaft power [W]")

    def compute(self, inputs, streams_in):
        """Report that the original equipment model is not implemented."""
        raise NotImplementedError(f"{self.name} is not modelled yet")
