"""BoosterPump component.

Maintains circulation pressure through the surface geothermal loop. The original GEMINI unit had no
equipment model.
"""

from pydantic import BaseModel, ConfigDict, Field

from gemini.core.modules.module import Module, ModuleResult


class BoosterPump(Module):
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

    fidelity = "passthrough"

    class Outputs(BaseModel):
        """Explicit statement that no equipment physics is modelled."""

        modelled: bool = Field(False, description="Equipment physics available [-]")

    def forward(self, inputs, streams_in):
        """Preserve the inlet stream without implying a performance model."""
        return ModuleResult(self.Outputs(), {"discharge": streams_in["suction"]})
