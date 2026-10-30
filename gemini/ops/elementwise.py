"""Elementwise functions and operators of the physics: ``exp``, ``log``, ``sqrt``, ``maximum``, ...

Write ``ops.maximum(a, b)`` instead of ``max(a, b)``, ``ops.sqrt`` instead of ``math.sqrt`` and
``ops.logical_or`` instead of ``or``, so one source runs on floats, arrays and traced values.
None of them raises on an input outside its domain: ``log(0)`` is ``-inf``, ``log(-1)`` and
``sqrt(-1)`` are ``nan`` and ``exp(1000)`` is ``inf``, as in NumPy, because both branches of
``where`` are always evaluated.
"""

from gemini.ops.dispatch import dispatch
from gemini.ops.registry import register

for _name in (
    "exp",
    "expm1",
    "log",
    "log10",
    "sqrt",
    "sin",
    "cos",
    "tan",
    "asin",
    "acos",
    "atan",
    "sinh",
    "cosh",
    "tanh",
    "abs",
    "sign",
    "floor",
    "ceil",
    "isnan",
    "isinf",
    "isfinite",
    "logical_not",
):
    register(_name, "elementwise", 1)
for _name in ("atan2", "maximum", "minimum", "logical_or", "round"):
    register(_name, "elementwise", 2)
register("clip", "elementwise", 3)


def exp(value):
    """Return ``e ** value``."""
    return dispatch("exp", value)


def expm1(value):
    """Return ``exp(value) - 1``."""
    return dispatch("expm1", value)


def log(value):
    """Return the natural logarithm; zero gives ``-inf`` and a negative value ``nan``."""
    return dispatch("log", value)


def log10(value):
    """Return the base-10 logarithm; zero gives ``-inf`` and a negative value ``nan``."""
    return dispatch("log10", value)


def sqrt(value):
    """Return the square root; a negative value gives ``nan``."""
    return dispatch("sqrt", value)


def sin(value):
    """Return the sine of ``value`` in radians."""
    return dispatch("sin", value)


def cos(value):
    """Return the cosine of ``value`` in radians."""
    return dispatch("cos", value)


def tan(value):
    """Return the tangent of ``value`` in radians."""
    return dispatch("tan", value)


def asin(value):
    """Return the arc sine in radians; ``nan`` outside ``[-1, 1]``."""
    return dispatch("asin", value)


def acos(value):
    """Return the arc cosine in radians; ``nan`` outside ``[-1, 1]``."""
    return dispatch("acos", value)


def atan(value):
    """Return the arc tangent in radians."""
    return dispatch("atan", value)


def sinh(value):
    """Return the hyperbolic sine of ``value``."""
    return dispatch("sinh", value)


def cosh(value):
    """Return the hyperbolic cosine of ``value``."""
    return dispatch("cosh", value)


def tanh(value):
    """Return the hyperbolic tangent of ``value``."""
    return dispatch("tanh", value)


def abs(value):
    """Return the absolute value of ``value``."""
    return dispatch("abs", value)


def sign(value):
    """Return 1, -1 or 0 by the sign of ``value``; ``nan`` stays ``nan``."""
    return dispatch("sign", value)


def floor(value):
    """Return the largest integer not above ``value``."""
    return dispatch("floor", value)


def ceil(value):
    """Return the smallest integer not below ``value``."""
    return dispatch("ceil", value)


def isnan(value):
    """Return whether ``value`` is ``nan``."""
    return dispatch("isnan", value)


def isinf(value):
    """Return whether ``value`` is infinite."""
    return dispatch("isinf", value)


def isfinite(value):
    """Return whether ``value`` is finite."""
    return dispatch("isfinite", value)


def logical_not(value):
    """Return whether the condition does not hold; use it instead of ``not``."""
    return dispatch("logical_not", value)


def atan2(y, x):
    """Return the angle in radians of the point ``(x, y)``."""
    return dispatch("atan2", y, x)


def maximum(left, right):
    """Return the larger of two values like ``max(left, right)``; use it instead of ``max``."""
    return dispatch("maximum", left, right)


def minimum(left, right):
    """Return the smaller of two values like ``min(left, right)``; use it instead of ``min``."""
    return dispatch("minimum", left, right)


def logical_or(left, right):
    """Return whether either condition holds; use it instead of ``or``."""
    return dispatch("logical_or", left, right)


def round(value, digits):
    """Return ``value`` rounded to ``digits`` decimals like Python's ``round``, ties to even."""
    return dispatch("round", value, digits)


def clip(value, low, high):
    """Return ``value`` limited to ``[low, high]``; ``nan`` stays ``nan``."""
    return dispatch("clip", value, low, high)
