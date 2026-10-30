"""Scalar backend: plain Python operators on floats, NumPy scalars and bools.

This is the untraced, tick-by-tick path and the reference of every other backend. Operators are
applied as written, so NumPy float32 scalars keep their float32 arithmetic and promotion. A graph
evaluates both branches of ``where``, so division by zero gives the IEEE result (``inf`` or
``nan``, as NumPy does) instead of ``ZeroDivisionError``.
"""

import math

from gemini.backends.base import Backend


class PythonBackend(Backend):
    """Evaluate ops on scalars with Python operators."""

    name = "python"

    def add(self, left, right):
        """Return ``left + right``."""
        return left + right

    def sub(self, left, right):
        """Return ``left - right``."""
        return left - right

    def mul(self, left, right):
        """Return ``left * right``."""
        return left * right

    def truediv(self, left, right):
        """Return ``left / right``; a zero divisor gives ``inf`` or ``nan`` as in IEEE 754."""
        try:
            return left / right
        except ZeroDivisionError:
            if left == 0 or math.isnan(left):
                return math.nan
            return math.copysign(math.inf, left) * math.copysign(1.0, right)

    def pow(self, base, exponent):
        """Return ``base ** exponent``."""
        return base**exponent

    def neg(self, value):
        """Return ``-value``."""
        return -value

    def lt(self, left, right):
        """Return ``left < right``."""
        return left < right

    def le(self, left, right):
        """Return ``left <= right``."""
        return left <= right

    def gt(self, left, right):
        """Return ``left > right``."""
        return left > right

    def ge(self, left, right):
        """Return ``left >= right``."""
        return left >= right

    def eq(self, left, right):
        """Return ``left == right``."""
        return left == right

    def ne(self, left, right):
        """Return ``left != right``."""
        return left != right

    def logical_and(self, left, right):
        """Return whether both conditions hold."""
        return bool(left) and bool(right)

    def where(self, condition, if_true, if_false):
        """Return the selected branch; a callable branch is called only when selected."""
        branch = if_true if condition else if_false
        return branch() if callable(branch) else branch

    def check(self, condition, code):
        """Return 0 where ``condition`` holds, else the error ``code``."""
        return 0 if condition else code

    def getitem(self, value, index):
        """Return item ``index`` of a vector value."""
        return value[index]
