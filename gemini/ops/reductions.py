"""Reductions over the last axis and interpolation: ``sum``, ``mean``, ``cumsum``, ``interp``.

A reduction takes a time series (an array) on the NumPy backend and a Python sequence on the
Python backend. ``interp(x, xp, fp)`` is ``numpy.interp``: ``xp`` increasing, the end values held
outside its range, the same bits on a scalar ``x`` as on an array.
"""

from gemini.ops.dispatch import dispatch
from gemini.ops.registry import register

for _name in ("sum", "mean", "cumsum"):
    register(_name, "reduction", 1)
register("interp", "interp", 3)


def sum(values):
    """Return the sum over the last axis."""
    return dispatch("sum", values)


def mean(values):
    """Return the mean over the last axis."""
    return dispatch("mean", values)


def cumsum(values):
    """Return the running sums over the last axis."""
    return dispatch("cumsum", values)


def interp(x, xp, fp):
    """Return the linear interpolation of the points ``(xp, fp)`` at ``x``."""
    return dispatch("interp", x, xp, fp)
