"""One limit of a problem: on a result field or a parameter, each match checked on its own."""

from dataclasses import asdict, dataclass

from gemini import units
from gemini._utils.strings import close_matches, did_you_mean, join_names
from gemini.errors import ValidationError

OVERS = ("each", "sum", "mean", "max", "min", "duration")
"""How a constraint reads a run: every step, one figure, or the time a condition holds."""
WHEN = (None, "running")
"""When a step counts: always, or while the module of the path carries flow."""
BOUNDS = ("min", "max", "equals")
"""The bounds of a constraint."""


@dataclass(frozen=True)
class Constraint:
    """A limit on ``path``: a result field or a parameter path, where ``*`` stays within a name.

    ``over`` is ``each`` (every step), ``sum``, ``mean``, ``max``, ``min`` (one figure of the run)
    or ``duration`` (the total time of the steps where ``when`` holds, ``min`` and ``max`` then
    being durations). ``when`` is ``None`` or ``"running"``, the steps where the module of the
    path carries flow. A bound is a number in SI or a text with its unit. A parameter path takes
    only ``over="each"``, which needs the plant, so ``gm.evaluate.constraints`` and ``gm.schedule``
    check it. At least one of ``min``, ``max`` and ``equals``.
    """

    path: str
    min: float | str | None = None
    max: float | str | None = None
    equals: float | str | None = None
    over: str = "each"
    when: str | None = None

    def __post_init__(self):
        """Refuse what no plant could make right."""
        if not isinstance(self.path, str) or "." not in self.path:
            raise ValidationError(
                f"constraint: path = {self.path!r}; expected '<module path>.<field>'",
                path="path",
                code="invalid_value",
            )
        if all(getattr(self, name) is None for name in BOUNDS):
            raise ValidationError(
                f"constraint {self.path}: expected min, max or equals",
                path=self.path,
                code="missing_value",
            )
        _checked_choice(self.path, "over", self.over, OVERS)
        _checked_choice(self.path, "when", self.when, WHEN)
        for name in BOUNDS:
            _checked_bound(self.path, name, getattr(self, name))

    @classmethod
    def from_dict(cls, data):
        """Return the constraint of a dictionary of ``to_dict``."""
        known = {"path", "over", "when", *BOUNDS}
        unknown = [name for name in data if name not in known]
        if unknown:
            raise ValidationError(
                f"constraint: key {unknown[0]!r} is unknown; expected one of {join_names(known)}"
                f"{did_you_mean(unknown[0], known)}",
                path=unknown[0],
                suggestions=close_matches(unknown[0], known),
                code="unknown_name",
            )
        if "path" not in data:
            raise ValidationError("constraint: path is missing", path="path", code="missing_value")
        return cls(**data)

    def to_dict(self):
        """Return the constraint as plain data."""
        return asdict(self)

    @classmethod
    def schema(cls):
        """Return the JSON Schema (draft 2020-12) of ``to_dict``."""
        bound = {"type": ["number", "string", "null"]}
        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": "Constraint",
            "type": "object",
            "required": ["path"],
            "additionalProperties": False,
            "properties": {
                "path": {"type": "string"},
                "min": bound,
                "max": bound,
                "equals": bound,
                "over": {"enum": list(OVERS)},
                "when": {"enum": list(WHEN)},
            },
        }


def _checked_choice(path, name, chosen, choices):
    """Raise ``invalid_value`` unless ``chosen`` is one of ``choices``."""
    if chosen not in choices:
        raise ValidationError(
            f"constraint {path}: {name} = {chosen!r}; expected one of "
            f"{join_names(map(str, choices))}",
            path=path,
            code="invalid_value",
        )


def _checked_bound(path, name, bound):
    """Raise unless a bound is ``None``, a number, or a number with a known unit."""
    if bound is None or (isinstance(bound, (int, float)) and not isinstance(bound, bool)):
        return
    if not isinstance(bound, str):
        raise ValidationError(
            f"constraint {path}: {name} = {bound!r}; expected a number or a text with its unit",
            path=path,
            code="invalid_value",
        )
    units.si_unit(units.parse(bound)[1])
