"""Health and immutable per-call module results."""

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from gemini.core.physics import units
from gemini.core.types.ports import Ports
from gemini.core.types.quantities import Fraction
from gemini.errors import UnitError, UnknownPortError
from gemini.utils.mappings import AttributeMapping
from gemini.utils.strings import did_you_mean, join_names, join_path


class Health(BaseModel):
    """Comparison of predicted equipment performance with measurements."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    assessed: bool = Field(True, description="Diagnostic model was evaluated [-]")
    score: Fraction = Field(..., description="Condition score, one is nominal [-]")
    alarm: bool = Field(..., description="Whether a monitoring limit is exceeded [-]")
    message: str = Field(..., description="Explanation of the condition [-]")
    metrics: dict[str, float] = Field(default_factory=dict)


class Values(AttributeMapping):
    """Read-only attribute and mapping access to named call values."""

    key_error = UnknownPortError
    attribute_error = UnknownPortError

    def __init__(self, values=None, declarations=None):
        """Store immutable-by-interface values and declaration metadata."""
        super().__init__(values)
        object.__setattr__(self, "_declarations", dict(declarations or {}))

    def _unknown(self, name):
        """Name the unknown value, the valid names and the closest match."""
        return (
            f"unknown value {name!r}; valid names: {join_names(self._values)}"
            f"{did_you_mean(name, self._values)}"
        )

    def model_dump(self, **kwargs):
        """Return a copy for engine storage and health calculations; options are ignored."""
        return self._values.copy()

    def get(self, name, default=None, *, unit=None):
        """Return one value, optionally converted from its declared SI unit.

        Differences such as a temperature difference convert by scale only.
        """
        if name not in self._values:
            return default
        value = self._values[name]
        if unit is None:
            return value
        declaration = self._declarations.get(name)
        if declaration is None or declaration.unit is None:
            raise UnitError(f"{name}: unit = None; expected a declared physical unit")
        return units.convert(value, declaration.unit, unit, declaration.quantity)


@dataclass(frozen=True)
class ModuleResult:
    """Computed outputs, outgoing flows and the evaluation audit data of one call.

    ``outputs`` and ``outlets`` are read-only mappings. ``inputs`` and ``children`` are plain
    dictionaries captured at evaluation time; treat them as read-only. ``leaves()`` treats a
    result without called children as a leaf.
    """

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
            result.update(child.leaves(join_path(prefix, name)))
        return result
