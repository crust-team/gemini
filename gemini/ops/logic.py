"""Comparison ops, ``logical_and`` and ``where``, the branch choice of traced physics.

``where(condition, if_true, if_false)`` replaces a value-dependent ``if``: write
``where(re < 2300, 64 / re, turbulent(re))`` instead of an ``if`` statement. A branch may be a
zero-argument callable, such as ``lambda: head / power``: the Python backend calls only the
selected one, so a branch that would divide by zero on a Python float is never evaluated, while
a trace and the NumPy backend evaluate both (NumPy warnings silenced).
"""

from gemini.ops.dispatch import Symbolic, dispatch
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
    """Return ``if_true`` where ``condition`` holds and ``if_false`` elsewhere.

    A traced condition records both branches, calling callable branches to trace them.
    """
    if isinstance(condition, Symbolic):
        if_true = if_true() if callable(if_true) else if_true
        if_false = if_false() if callable(if_false) else if_false
    return dispatch("where", condition, if_true, if_false)
