"""Health of a module over the rows of a chunk, as the columns of its result.

``assess`` calls ``Module.health`` once on the arrays of a chunk on the NumPy backend. A module
without a diagnostic is ``UNAVAILABLE``. On the Python backend, or when the call on arrays raises
(a ``Health`` check refused a row), ``assess`` calls it row by row on plain values: the rows that
raise are the rows that fail, with the real exception, and the others are stacked into columns.
"""

from typing import Any, NamedTuple

import numpy as np

from gemini import backends
from gemini.core.modules.module import Module
from gemini.core.types import Health
from gemini.core.types.results import NOT_ASSESSED

UNAVAILABLE = Health(score=1, alarm=False, assessed=False, message=NOT_ASSESSED)
"""The one health of every module without a diagnostic model, shared by all results."""


class HealthColumns(NamedTuple):
    """The health of several rows stacked: the fields of ``Health``, one entry per row."""

    assessed: Any
    score: Any
    alarm: Any
    message: Any
    metrics: dict


def assess(module, result, measured, count):
    """Return ``(health, errors)`` of ``count`` rows of array ``result`` and ``measured``.

    ``errors`` maps the position of a row whose health raised to the exception. Lack of
    diagnostics stays distinct from assessed nominal health: a module that does not override
    ``health`` is not called.
    """
    if type(module).health is Module.health or not result.outputs:
        return UNAVAILABLE, {}
    if backends.forced_name() != "python":
        try:
            return module.health(result, measured) or UNAVAILABLE, {}
        except Exception:
            pass
    return _rows(module, result, measured, count)


def _rows(module, result, measured, count):
    """Call ``health`` on each row's plain values; stack the healths of the rows that worked."""
    healths, errors = [], {}
    for position in range(count):
        row = {name: float(values[position]) for name, values in measured.items()}
        try:
            healths.append(module.health(result.row(position), row) or UNAVAILABLE)
        except Exception as error:
            errors[position] = error
            healths.append(UNAVAILABLE)
    return _stacked(healths), errors


def _stacked(healths):
    """Return the healths of the rows as one ``HealthColumns``; a missing metric is NaN."""
    names = dict.fromkeys(name for health in healths for name in health.metrics)
    metrics = {
        name: np.array([health.metrics.get(name, np.nan) for health in healths], dtype=float)
        for name in names
    }
    return HealthColumns(
        assessed=np.array([health.assessed for health in healths], dtype=bool),
        score=np.array([health.score for health in healths], dtype=float),
        alarm=np.array([health.alarm for health in healths], dtype=bool),
        message=[health.message for health in healths],
        metrics=metrics,
    )
