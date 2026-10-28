"""Degasser component.

Separates released gas from the produced geothermal brine. The original GEMINI unit had no equipment
model.
"""

from pydantic import BaseModel, ConfigDict, Field

from gemini.core.base.component import Component


class Degasser(Component):
    """Separates released gas from the produced geothermal brine."""

    name = "degasser"
    category = "treatment"
    description = "Separates released gas from the produced geothermal brine."
    inlets = ("inlet",)
    outlets = ("liquid", "gas")

    class Params(BaseModel):
        """Available design parameters; no performance model is assumed."""

        model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
        heat_transfer_coeff: float = Field(
            ..., ge=0, description="Legacy coefficient with unknown physical meaning [unknown]"
        )

    class Inputs(BaseModel):
        """No operating inputs are modelled yet."""

        model_config = ConfigDict(extra="forbid")

    class Outputs(BaseModel):
        """Declared future performance results."""

        gas_mass_flow: float = Field(..., description="Separated gas flow [kg/s]")
        pressure_drop: float = Field(..., description="Pressure loss [Pa]")

    def compute(self, inputs, streams_in):
        """Report that the original equipment model is not implemented."""
        raise NotImplementedError(f"{self.name} is not modelled yet")
