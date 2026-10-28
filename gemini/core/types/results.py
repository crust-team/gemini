"""Health and immutable per-call module results."""

from dataclasses import dataclass, field
from typing import Any, Iterator, Mapping

from pydantic import BaseModel, ConfigDict, Field

from gemini.core.physics import units
from gemini.core.types.ports import Ports
from gemini.core.types.quantities import Fraction


class Health(BaseModel):
    """Comparison of predicted equipment performance with measurements."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    assessed: bool = Field(True, description="Diagnostic model was evaluated [-]")
    score: Fraction = Field(..., ge=0, le=1, description="Condition score, one is nominal [-]")
    alarm: bool = Field(..., description="Whether a monitoring limit is exceeded [-]")
    message: str = Field(..., description="Explanation of the condition [-]")
    metrics: dict[str, float] = Field(default_factory=dict)


class Values(Mapping[str, Any]):
    """Read-only attribute and mapping access to named call values."""

    def __init__(self, values=None, declarations=None):
        """Store immutable-by-interface values and declaration metadata."""
        self._values = dict(values or {})
        self._declarations = dict(declarations or {})

    def __getitem__(self, name):
        """Return a value by mapping key."""
        return self._values[name]

    def __getattr__(self, name):
        """Return a value by attribute name."""
        values = self.__dict__.get("_values")
        if values is None:
            raise AttributeError(name)
        try:
            return values[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __iter__(self) -> Iterator[str]:
        """Iterate value names."""
        return iter(self._values)

    def __len__(self):
        """Return the number of recorded values."""
        return len(self._values)

    def model_dump(self, **kwargs):
        """Return a copy for engine storage and health calculations."""
        del kwargs
        return self._values.copy()

    def get(self, name, default=None, *, unit=None):
        """Return one value, optionally converted from its declared SI unit."""
        if name not in self._values:
            return default
        value = self._values[name]
        if unit is None:
            return value
        declaration = self._declarations.get(name)
        if declaration is None or declaration.unit is None:
            raise ValueError(f"{name}: no physical unit is declared")
        return units.convert(value, declaration.unit, unit)

    def __repr__(self):
        """Represent the contained values as a plain mapping."""
        return repr(self._values)


@dataclass(frozen=True)
class ModuleResult:
    """Computed outputs, outgoing flows and immutable evaluation audit data."""

    outputs: Values
    outlets: Ports
    inlets: Ports = field(default_factory=Ports)
    inputs: dict[str, Any] = field(default_factory=dict)
    children: dict[str, "ModuleResult"] = field(default_factory=dict)
    call_records: tuple[tuple[str, "ModuleResult"], ...] = field(default_factory=tuple, repr=False)
    is_leaf: bool = True

    def leaves(self, prefix=""):
        """Flatten only descendant leaf results, with relative module paths."""
        if not self.children:
            return {prefix: self}
        result = {}
        for name, child in self.children.items():
            result.update(child.leaves(f"{prefix}.{name}" if prefix else name))
        return result
