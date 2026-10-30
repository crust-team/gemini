"""Array backend: NumPy ufuncs over whole time series, with floating-point warnings silenced.

Both branches of ``where`` are evaluated on every row, so the branch that is not selected may
divide by zero or overflow; those warnings are silenced here and never reach the user. Vector
values (a parameter of shape ``(n,)``) are indexed on their last axis, which leaves room for a
leading scenario axis.
"""

import numpy as np

from gemini.backends.base import Backend


class NumpyBackend(Backend):
    """Evaluate ops on NumPy arrays and scalars."""

    name = "numpy"

    def add(self, left, right):
        """Return ``left + right``."""
        with np.errstate(all="ignore"):
            return np.add(left, right)

    def sub(self, left, right):
        """Return ``left - right``."""
        with np.errstate(all="ignore"):
            return np.subtract(left, right)

    def mul(self, left, right):
        """Return ``left * right``."""
        with np.errstate(all="ignore"):
            return np.multiply(left, right)

    def truediv(self, left, right):
        """Return ``left / right``; a zero divisor gives ``inf`` or ``nan`` silently."""
        with np.errstate(all="ignore"):
            return np.true_divide(left, right)

    def pow(self, base, exponent):
        """Return ``base ** exponent``."""
        with np.errstate(all="ignore"):
            return np.power(base, exponent)

    def neg(self, value):
        """Return ``-value``."""
        return np.negative(value)

    def lt(self, left, right):
        """Return ``left < right`` per row."""
        return np.less(left, right)

    def le(self, left, right):
        """Return ``left <= right`` per row."""
        return np.less_equal(left, right)

    def gt(self, left, right):
        """Return ``left > right`` per row."""
        return np.greater(left, right)

    def ge(self, left, right):
        """Return ``left >= right`` per row."""
        return np.greater_equal(left, right)

    def eq(self, left, right):
        """Return ``left == right`` per row."""
        return np.equal(left, right)

    def ne(self, left, right):
        """Return ``left != right`` per row."""
        return np.not_equal(left, right)

    def logical_and(self, left, right):
        """Return whether both conditions hold, per row."""
        return np.logical_and(left, right)

    def where(self, condition, if_true, if_false):
        """Select per row; callable branches are both evaluated, with warnings silenced."""
        with np.errstate(all="ignore"):
            selected = if_true() if callable(if_true) else if_true
            other = if_false() if callable(if_false) else if_false
            return np.where(condition, selected, other)

    def check(self, condition, code):
        """Return 0 on rows where ``condition`` holds, else the error ``code``."""
        return np.where(condition, 0, code)

    def getitem(self, value, index):
        """Return item ``index`` of the last axis of a vector value."""
        return np.asarray(value)[..., index]
