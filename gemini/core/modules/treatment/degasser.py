"""Degasser component.

Separates released gas from the produced geothermal brine. The original GEMINI unit had no equipment
model.
"""

from pydantic import BaseModel, ConfigDict, Field

from gemini.core.modules.module import Module, ModuleResult


class Degasser(Module):
    """Separates released gas from the produced geothermal brine."""

    fidelity = "passthrough"
    soft_sensors = ("pressure_drop", "gas_mass_flow")
    name = "degasser"
    category = "treatment"
    description = "Separates released gas from the produced geothermal brine."
    inlets = ("inlet",)
    outlets = ("liquid", "gas")

    class Params(BaseModel):
        """Available design parameters; no performance model is assumed."""

        model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
        p_out: float | None = Field(None, ge=0, description="Separator outlet pressure [Pa]")
        dp: float = Field(14900, ge=0, description="Separator pressure loss [Pa]")
        heat_transfer_coeff: float = Field(
            0, ge=0, description="Legacy coefficient with unknown physical meaning [unknown]"
        )

    class Inputs(BaseModel):
        """No operating inputs are modelled yet."""

        model_config = ConfigDict(extra="forbid")

    class Outputs(BaseModel):
        """Declared future performance results."""

        gas_mass_flow: float = Field(..., description="Separated gas flow [kg/s]")
        pressure_drop: float = Field(..., description="Pressure loss [Pa]")

    def forward(self, inputs, streams_in):
        """Pass liquid through; gas separation is not modelled and gas flow is zero."""
        # NOTE(refactor): 0.149 bar default loss comes from Sep_Pin/Sep_Pout in the example.
        stream = streams_in["inlet"]
        pressure = self.params.p_out if self.params.p_out is not None else stream.p - self.params.dp
        liquid = stream.with_(p=pressure)
        return ModuleResult(
            self.Outputs(gas_mass_flow=0, pressure_drop=stream.p - pressure),
            {"liquid": liquid, "gas": liquid.with_(m_dot=0)},
        )
