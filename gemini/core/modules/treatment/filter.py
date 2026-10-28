"""Filter component.

Removes suspended solids before reinjection into the aquifer. The original GEMINI unit had no
equipment model.
"""

from pydantic import BaseModel, ConfigDict, Field

from gemini.core.base.health import Health
from gemini.core.modules.module import Module
from gemini.core.physics import units


class Filter(Module):
    """Removes suspended solids before reinjection into the aquifer."""

    name = "filter"
    category = "treatment"
    description = "Removes suspended solids before reinjection into the aquifer."
    inlets = ("inlet",)
    outlets = ("outlet",)

    class Params(BaseModel):
        """Available design parameters; no performance model is assumed."""

        model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
        clogging_dp: float = Field(
            units.bar_to_pa(0.5), gt=0, description="Clogging alarm pressure differential [Pa]"
        )

    class Inputs(BaseModel):
        """No operating inputs are modelled yet."""

        model_config = ConfigDict(extra="forbid")

    class Outputs(BaseModel):
        """Declared future performance results."""

        pressure_drop: float = Field(..., description="Pressure loss [Pa]")

    def forward(self, inputs, streams_in):
        """Report that the original equipment model is not implemented."""
        raise NotImplementedError(f"{self.name} is not modelled yet")

    def health(self, predicted, measured):
        """Alarm when measured filter pressure loss exceeds the clogging limit."""
        if "pressure_drop" not in measured:
            return None
        dp = measured["pressure_drop"]
        ratio = max(0, dp) / self.params.clogging_dp
        return Health(
            score=max(0, 1 - ratio),
            alarm=dp > self.params.clogging_dp,
            message=(
                "Filter pressure drop exceeds limit"
                if dp > self.params.clogging_dp
                else "Filter pressure drop within limit"
            ),
            metrics={"pressure_drop": dp},
        )
