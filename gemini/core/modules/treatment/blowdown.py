"""Blowdown placeholder that conserves the incoming stream.

No withdrawal physics is modelled; outputs explicitly report modelled=False.
"""

from pydantic import BaseModel, ConfigDict, Field

from gemini.core.modules.module import Module
from gemini.core.types.results import ModuleResult


class Blowdown(Module):
    """Removes a controlled fraction of circulating brine."""

    name = "blowdown"
    category = "treatment"
    description = "Removes a controlled fraction of circulating brine."
    inlets = ("inlet",)
    outlets = ("outlet",)

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
        return ModuleResult(self.Outputs(), {"outlet": streams_in["inlet"]})
