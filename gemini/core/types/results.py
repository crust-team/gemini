"""Equipment monitoring health."""

from dataclasses import dataclass
from typing import Any, NamedTuple

from pydantic import BaseModel, ConfigDict, Field

from gemini.core.types.flows import Stream
from gemini.core.types.quantities import Dimensionless, Fraction


class Health(BaseModel):
    """Comparison of predicted equipment performance with measurements."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    assessed: bool = Field(True, description="Diagnostic model was evaluated [-]")
    score: Fraction = Field(..., ge=0, le=1, description="Condition score, one is nominal [-]")
    alarm: bool = Field(..., description="Whether a monitoring limit is exceeded [-]")
    message: str = Field(..., description="Explanation of the condition [-]")
    metrics: dict[str, float] = Field(
        default_factory=dict, description="Named diagnostic metrics [-]"
    )


class ModuleResult(NamedTuple):
    """Validated outputs and outgoing SI streams from one evaluation."""

    outputs: BaseModel
    streams: dict[str, Stream]


@dataclass(frozen=True)
class ParamRef:
    """A calibratable parameter's location, current value and numeric bounds."""

    path: str
    module_path: str
    field: str
    value: Any
    # Bounds use the owning Params field unit; they are not dimensionless physical values.
    bounds: tuple[Dimensionless, Dimensionless] | None
