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

import numpy as np

from gemini.errors import ValidationError
from gemini.errors.base import problem
from gemini.physics import units
from gemini.utils.jsonable import to_plain
from gemini.utils.strings import close_matches, did_you_mean, join_names

__all__ = ["value", "series", "statistics", "problem", "check", "OutputUnits", "SCHEMAS"]

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


def _converted(number, unit, target, quantity):
    """Return a number, an array or a nested list in ``target``; what is no number stays."""
    if number is None or isinstance(number, (bool, str)):
        return number
    if isinstance(number, np.ndarray):
        return units.array_convert(number, unit, target, quantity)
    if isinstance(number, (list, tuple)):
        return [_converted(item, unit, target, quantity) for item in number]
    return units.convert(number, unit, target, quantity)


class OutputUnits:
    """The ``units`` argument of a public return: a map from quantity to unit, used on the way out.

    Outputs are SI unless a call asks otherwise, and nothing inside a run changes. A key names a
    quantity; it also reaches the quantities of its family (``units.family``), so ``"power"``
    reaches ``duty`` and ``"pressure"`` a pressure difference, unless the map names them too. A
    difference converts by scale only. An unknown quantity or a unit that does not fit it raises
    ``ValidationError`` with suggestions, here at the start of the call. The ``value``, ``series``
    and ``statistics`` of this class are the helpers of the module, in the unit actually used.
    """

    def __init__(self, map_of_units=None):
        """Check every quantity and unit of the map."""
        self.units = dict(map_of_units or {})
        for quantity, unit in self.units.items():
            if not units.fits(unit, quantity):
                raise _wrong_unit(quantity, unit)

    def target(self, quantity):
        """Return the unit the map asks for ``quantity``, or ``None`` to keep the stored one."""
        if not self.units or quantity is None:
            return None
        return self.units.get(quantity) or self.units.get(units.family(quantity))

    def number(self, number, unit, quantity):
        """Return ``(number, unit)`` in the unit the map asks for ``quantity``."""
        target = self.target(quantity)
        if target is None:
            return number, unit
        return _converted(number, unit, target, quantity), target

    def value(self, number, unit, quantity, reason=None, **details):
        """Return the value of a number in ``unit``, a stored unit of ``quantity``."""
        converted, used = self.number(number, unit, quantity)
        return value(converted, used, reason, **details)

    def series(self, time, number, unit, quantity):
        """Return the time series of ``number``, stored in ``unit``."""
        converted, used = self.number(number, unit, quantity)
        return series(time, converted, used)

    def statistics(self, minimum, maximum, mean, unit, quantity):
        """Return ``{min, max, mean}`` of numbers stored in ``unit``."""
        return {
            "min": self.value(minimum, unit, quantity),
            "max": self.value(maximum, unit, quantity),
            "mean": self.value(mean, unit, quantity),
        }


def _wrong_unit(quantity, unit):
    """Return the error of a unit that does not fit ``quantity``, with the closest units."""
    valid = units.names(quantity)
    return ValidationError(
        f"units: {quantity} = {unit!r}; expected one of {join_names(valid)}"
        f"{did_you_mean(unit, valid)}",
        path=f"units.{quantity}",
        suggestions=close_matches(unit, valid),
        code="invalid_unit",
    )
