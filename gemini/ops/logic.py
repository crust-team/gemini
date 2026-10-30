"""Comparison ops, ``logical_and`` and ``where``, the branch choice of traced physics.

``where(condition, if_true, if_false)`` replaces a value-dependent ``if``: write
``where(re < 2300, 64 / re, turbulent(re))`` instead of an ``if`` statement. Both branches are
plain values and are always evaluated. A branch that can be invalid where it is not selected
uses ``ops.truediv`` or ``ops.pow`` rather than ``/`` or ``**``, which give ``inf`` or ``nan``
silently instead of raising on Python floats. A branch may be ``None``: it stays ``None`` on
Python values and is NaN in arrays and graphs.
"""

from gemini.ops.dispatch import dispatch
from gemini.ops.registry import register

for _name in ("lt", "le", "gt", "ge", "eq", "ne", "logical_and"):
    register(_name, "elementwise", 2)
register("where", "elementwise", 3)


def lt(left, right):
    """Return ``left < right``."""
    return dispatch("lt", left, right)


def le(left, right):
    """Return ``left <= right``."""
    return dispatch("le", left, right)


def gt(left, right):
    """Return ``left > right``."""
    return dispatch("gt", left, right)


def ge(left, right):
    """Return ``left >= right``."""
    return dispatch("ge", left, right)


def eq(left, right):
    """Return ``left == right``."""
    return dispatch("eq", left, right)


def ne(left, right):
    """Return ``left != right``."""
    return dispatch("ne", left, right)


def logical_and(left, right):
    """Return whether both conditions hold; use it instead of ``and`` or ``a <= b <= c``."""
    return dispatch("logical_and", left, right)


def where(condition, if_true, if_false):
    """Return ``if_true`` where ``condition`` holds and ``if_false`` elsewhere."""
    return dispatch("where", condition, if_true, if_false)
