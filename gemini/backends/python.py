"""Scalar backend: plain Python operators on floats, NumPy scalars and bools.

This is the untraced, tick-by-tick path and the reference of every other backend. Operators are
applied as written, so NumPy float32 scalars keep their float32 arithmetic and promotion.

``where`` evaluates both of its branches, so an op never raises and never warns on an operand
that is invalid in the branch not selected: division by zero, a power that is infinite, complex
or overflows give ``inf`` or ``nan`` exactly as NumPy does. The valid operands give the plain
Python result.
"""

import math

import numpy as np

from gemini.backends.base import Backend

PLAIN_NUMBERS = frozenset({float, int})


def numpy_result(function, *values):
    """Return ``function`` of ``values`` as NumPy computes it, with its warnings silenced."""
    with np.errstate(all="ignore"):
        return function(*values)


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
        if type(left) not in PLAIN_NUMBERS or type(right) not in PLAIN_NUMBERS:
            return numpy_result(np.true_divide, left, right)
        if right != 0:
            return left / right
        if left == 0 or math.isnan(left):
            return math.nan
        return math.copysign(math.inf, left) * math.copysign(1.0, right)

    def pow(self, base, exponent):
        """Return ``base ** exponent``; an invalid or overflowing power gives ``inf`` or ``nan``."""
        if type(base) not in PLAIN_NUMBERS or type(exponent) not in PLAIN_NUMBERS:
            return numpy_result(np.power, base, exponent)
        try:
            result = base**exponent
        except (ZeroDivisionError, OverflowError):
            return float(numpy_result(np.power, float(base), float(exponent)))
        if type(result) is complex:
            return math.nan
        return result

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
        """Return the selected branch unchanged, ``None`` included."""
        return if_true if condition else if_false

    def check(self, condition, code):
        """Return 0 where ``condition`` holds, else the error ``code``."""
        return 0 if condition else code

    def getitem(self, value, index):
        """Return item ``index`` of a vector value."""
        return value[index]
