"""Blowdown component.

Removes a controlled fraction of circulating brine. The original GEMINI unit had no equipment model.
"""

from pydantic import BaseModel, ConfigDict, Field

from gemini.core.modules.module import Module


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

    class Outputs(BaseModel):
        """Declared future performance results."""

        mass_flow: float = Field(..., description="Discharged brine mass flow [kg/s]")

    def forward(self, inputs, streams_in):
        """Report that the original equipment model is not implemented."""
        raise NotImplementedError(f"{self.name} is not modelled yet")
