"""Equipment monitoring health."""

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from gemini.core.types.flows import Flow
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


@dataclass(frozen=True)
class ModuleResult:
    """Outputs, typed flows and an evaluation tree captured by Module.__call__.

    Iteration yields outputs and streams. Inputs and children are audit metadata,
    retained with this result so later evaluations cannot alter its balances.
    """

    outputs: BaseModel
    streams: dict[str, Flow]
    inlets: dict[str, Flow] = field(default_factory=dict)
    inputs: BaseModel | None = None
    children: dict[str, "ModuleResult"] = field(default_factory=dict)

    def __iter__(self):
        """Unpack the two public calculation values."""
        yield self.outputs
        yield self.streams

    def leaves(self, prefix=""):
        """Flatten only descendant leaf results, with relative module paths."""
        if not self.children:
            return {prefix: self}
        result = {}
        for name, child in self.children.items():
            result.update(child.leaves(f"{prefix}.{name}" if prefix else name))
        return result


@dataclass(frozen=True)
class ParamRef:
    """A calibratable parameter's location, current value and numeric bounds."""

    path: str
    module_path: str
    field: str
    value: Any
    # Bounds use the owning Params field unit; they are not dimensionless physical values.
    bounds: tuple[Dimensionless, Dimensionless] | None
