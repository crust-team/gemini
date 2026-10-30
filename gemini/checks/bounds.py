"""The declared limits of every output a run recorded."""

import numpy as np
import pandas as pd

from gemini.checks.outcome import check
from gemini.utils.strings import join_path

_OUTSIDE = {
    "ge": np.less,
    "gt": np.less_equal,
    "le": np.greater,
    "lt": np.greater_equal,
}
"""For each limit of ``Declaration.limits``, the comparison that a violating value satisfies."""


def _outside(values, limits):
    """Return how many values violate any of the ``limits``; a missing value never does."""
    array = values.to_numpy(dtype=float)
    violated = np.zeros(array.shape, dtype=bool)
    for key, limit in limits.items():
        violated |= _OUTSIDE[key](array, limit)
    return int(violated.sum())


def bounds(plant, results):
    """Check that every recorded output is inside the limits its module declares.

    The limits are those of the output's declaration (``ge``, ``gt``, ``le``, ``lt`` from its
    quantity and its bounds, see ``Declaration.limits``), read from the module at the
    column's path. Boolean and text columns, outputs without a limit and the health columns are
    not judged.

    Parameters
    ----------
    plant : Module
        The plant that produced ``results``; a path of the results it lacks raises
        ``UnknownNameError``.
    results : Results
        A finished run.

    Returns
    -------
    dict
        ``{name: "bounds", passed, value, tolerance}``: ``value`` is the number of values outside
        their limits, over all columns and ticks, and ``tolerance`` is 0. ``passed`` is
        ``None`` with a ``reason`` when no recorded output has a limit.
    """
    frame = results.to_frame()
    judged, violations = 0, 0
    for path, fields in results.names().items():
        outputs = plant.get_module(path).outputs(recurse=False)
        for field in fields:
            column = frame[join_path(path, field)]
            limits = outputs[field].limits() if field in outputs else {}
            if limits and pd.api.types.is_numeric_dtype(column) and column.dtype != bool:
                judged += 1
                violations += _outside(column, limits)
    if not judged:
        return check("bounds", None, None, 0, "no recorded output has a declared limit")
    return check("bounds", violations == 0, violations, 0)
