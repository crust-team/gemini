"""Arithmetic ops and vector indexing; ``truediv``, ``pow``, ``mod`` and ``floordiv`` never raise.

Physics code reaches these through the Python operators of traced values and constants; the
functions below are the same ops for explicit calls.
"""

from gemini.ops.dispatch import dispatch
from gemini.ops.registry import register

for _name in ("add", "sub", "mul", "truediv", "pow", "mod", "floordiv"):
    register(_name, "elementwise", 2)
register("neg", "elementwise", 1)
register("getitem", "index", 2)


def add(left, right):
    """Return ``left + right``."""
    return dispatch("add", left, right)


def sub(left, right):
    """Return ``left - right``."""
    return dispatch("sub", left, right)


def mul(left, right):
    """Return ``left * right``."""
    return dispatch("mul", left, right)


def truediv(left, right):
    """Return ``left / right``."""
    return dispatch("truediv", left, right)


def pow(base, exponent):
    """Return ``base ** exponent``."""
    return dispatch("pow", base, exponent)


def mod(left, right):
    """Return ``left % right``; a zero divisor gives ``nan`` instead of raising."""
    return dispatch("mod", left, right)


def floordiv(left, right):
    """Return ``left // right``; a zero divisor gives ``inf`` or ``nan`` instead of raising."""
    return dispatch("floordiv", left, right)


def neg(value):
    """Return ``-value``."""
    return dispatch("neg", value)


def getitem(value, index):
    """Return item ``index`` of a vector value, such as one curve coefficient."""
    return dispatch("getitem", value, index)
