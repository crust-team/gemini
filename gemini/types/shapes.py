"""The three shapes of every public return: value, problem and check.

Every public return that carries data is built from these, by the helpers here, so no module
assembles a shape by hand. Each shape has a JSON Schema, written to ``docs/schemas/``.

- **Value** ``{value, unit}``: a number, an array or ``None``, and when it is ``None`` a ``reason``
  says why. A time series adds ``time``; statistics are ``{min, max, mean}``, each a value.
- **Problem** ``{path, code, message, suggestions}``: every error, validation result and failed
  run row; a run row adds ``time``. ``code`` is the stable key for machines. ``problem`` is defined
  in ``gemini.errors``, a leaf package, because ``GeminiError.to_dict`` returns one.
- **Check** ``{name, passed, value, limit}``, where ``value`` and ``limit`` are values. A failed
  check is an answer, not an error.
"""

from gemini.errors.base import problem
from gemini.utils.jsonable import to_plain

__all__ = ["value", "series", "statistics", "problem", "check", "SCHEMAS"]

NO_VALUE = "no value"
"""The ``reason`` of a value that is ``None`` when the caller gives none."""

DIALECT = "https://json-schema.org/draft/2020-12/schema"

VALUE_SCHEMA = {
    "$schema": DIALECT,
    "title": "GEMINI value",
    "description": (
        "A number with its unit: {value, unit}. value is a number, an array or null, and when it "
        "is null a reason says why. A time series adds time. An output that is a flag or a text "
        "keeps its boolean or string; economics returns add the parts of the result as keys."
    ),
    "type": "object",
    "required": ["value", "unit"],
    "properties": {
        "value": {"type": ["number", "boolean", "string", "array", "null"]},
        "unit": {"type": "string"},
        "time": {"type": "array", "items": {"type": "string"}},
        "reason": {"type": "string"},
    },
    "anyOf": [
        {"properties": {"value": {"type": ["number", "boolean", "string", "array"]}}},
        {"required": ["reason"]},
    ],
}

PROBLEM_SCHEMA = {
    "$schema": DIALECT,
    "title": "GEMINI problem",
    "description": (
        "Every error, validation result and failed run row: the shape of 422 details and agent "
        "tool results. code is one of gm.errors.CODES or gm.errors.ROW_CODES; a run row adds time."
    ),
    "type": "object",
    "required": ["path", "code", "message", "suggestions"],
    "additionalProperties": False,
    "properties": {
        "path": {"type": ["string", "null"]},
        "code": {"type": "string"},
        "message": {"type": "string"},
        "suggestions": {"type": "array", "items": {"type": "string"}},
        "time": {"type": "string"},
    },
}

CHECK_SCHEMA = {
    "$schema": DIALECT,
    "title": "GEMINI check",
    "description": (
        "A judged quantity: {name, passed, value, limit}. value and limit are values. passed is "
        "null, with a reason in value, when there is nothing to judge."
    ),
    "type": "object",
    "required": ["name", "passed", "value", "limit"],
    "additionalProperties": False,
    "properties": {
        "name": {"type": "string"},
        "passed": {"type": ["boolean", "null"]},
        "value": {"$ref": "#/$defs/value"},
        "limit": {"$ref": "#/$defs/value"},
    },
    "$defs": {"value": {k: v for k, v in VALUE_SCHEMA.items() if k != "$schema"}},
}

SCHEMAS = {"value": VALUE_SCHEMA, "problem": PROBLEM_SCHEMA, "check": CHECK_SCHEMA}
"""The JSON Schema of each shape, by the name of its file in ``docs/schemas/``."""


def value(number, unit, reason=None, **details):
    """Return ``{value, unit}`` as plain JSON, with a ``reason`` when the value is ``None``.

    NaN and infinity are ``None``. ``details`` adds the parts of a result, each a value already
    or a text, after the shape's own keys.
    """
    plain = to_plain(number)
    shape = {"value": plain, "unit": unit}
    if plain is None:
        shape["reason"] = reason or NO_VALUE
    return shape | details


def series(time, number, unit):
    """Return the time series ``{time, value, unit}`` as plain JSON."""
    return {"time": to_plain(time), "value": to_plain(number), "unit": unit}


def statistics(minimum, maximum, mean, unit):
    """Return ``{min, max, mean}``, each a value in ``unit``."""
    return {
        "min": value(minimum, unit),
        "max": value(maximum, unit),
        "mean": value(mean, unit),
    }


def check(name, passed, measured, limit):
    """Return ``{name, passed, value, limit}``; ``measured`` and ``limit`` are values.

    ``passed`` is ``True`` or ``False``, or ``None`` when there is nothing to judge, with the
    reason in ``measured``.
    """
    return {"name": name, "passed": passed, "value": measured, "limit": limit}
