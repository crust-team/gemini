"""Clean-filter quadratic hydraulic loss and clogging diagnostics."""

from pydantic import BaseModel, ConfigDict, Field

from gemini.core.modules.module import Module
from gemini.core.physics import units
from gemini.core.types.results import Health, ModuleResult


class Filter(Module):
    """Removes suspended solids before reinjection into the aquifer."""

    fidelity = "simple"
    soft_sensors = ("pressure_drop",)
    name = "filter"
    category = "treatment"
    description = "Removes suspended solids before reinjection into the aquifer."
    inlets = ("inlet",)
    outlets = ("outlet",)

    class Params(BaseModel):
        """Available design parameters; no performance model is assumed."""

        model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
        # NOTE(refactor): nominal clean loss from the example (0.016 bar at 149 m3/h).
        dp_nominal: float = Field(1600, ge=0, description="Clean nominal pressure loss [Pa]")
        m_dot_nominal: float = Field(
            149 / 3600 * 1068, gt=0, description="Nominal brine mass flow [kg/s]"
        )
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
        """Apply a quadratic clean-filter pressure loss, conserving mass and temperature."""
        stream = streams_in["inlet"]
        dp = self.params.dp_nominal * (stream.m_dot / self.params.m_dot_nominal) ** 2
        return ModuleResult(
            self.Outputs(pressure_drop=dp), {"outlet": stream.with_(p=stream.p - dp)}
        )

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
