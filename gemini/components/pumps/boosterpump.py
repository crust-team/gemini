"""BoosterPump component.

Maintains circulation pressure through the surface geothermal loop. The original GEMINI unit had no
equipment model.
"""

from pydantic import BaseModel, ConfigDict, Field

from gemini.core.base.component import Component


class BoosterPump(Component):
    """Maintains circulation pressure through the surface geothermal loop."""

    name = "boosterpump"
    category = "pumps"
    description = "Maintains circulation pressure through the surface geothermal loop."
    inlets = ("suction",)
    outlets = ("discharge",)

    class Params(BaseModel):
        """Available design parameters; no performance model is assumed."""

        model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

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
