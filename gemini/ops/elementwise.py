"""Elementwise functions and operators of the physics: ``exp``, ``log``, ``sqrt``, ``maximum``, ...

Write ``ops.maximum(a, b)`` instead of ``max(a, b)``, ``ops.sqrt`` instead of ``math.sqrt`` and
``ops.logical_or`` instead of ``or``, so one source runs on floats, arrays and traced values.
None of them raises on an input outside its domain: ``log(0)`` is ``-inf``, ``log(-1)`` and
``sqrt(-1)`` are ``nan`` and ``exp(1000)`` is ``inf``, as in NumPy, because both branches of
``where`` are always evaluated.
"""

from gemini.ops.dispatch import elementwise_op

exp = elementwise_op("exp", 1, "Return ``e ** value``.")
expm1 = elementwise_op("expm1", 1, "Return ``exp(value) - 1``.")
log = elementwise_op(
    "log", 1, "Return the natural logarithm; zero gives ``-inf`` and a negative value ``nan``."
)
log10 = elementwise_op(
    "log10", 1, "Return the base-10 logarithm; zero gives ``-inf`` and a negative value ``nan``."
)
sqrt = elementwise_op("sqrt", 1, "Return the square root; a negative value gives ``nan``.")
sin = elementwise_op("sin", 1, "Return the sine of ``value`` in radians.")
cos = elementwise_op("cos", 1, "Return the cosine of ``value`` in radians.")
tan = elementwise_op("tan", 1, "Return the tangent of ``value`` in radians.")
asin = elementwise_op("asin", 1, "Return the arc sine in radians; ``nan`` outside ``[-1, 1]``.")
acos = elementwise_op("acos", 1, "Return the arc cosine in radians; ``nan`` outside ``[-1, 1]``.")
atan = elementwise_op("atan", 1, "Return the arc tangent in radians.")
sinh = elementwise_op("sinh", 1, "Return the hyperbolic sine of ``value``.")
cosh = elementwise_op("cosh", 1, "Return the hyperbolic cosine of ``value``.")
tanh = elementwise_op("tanh", 1, "Return the hyperbolic tangent of ``value``.")
abs = elementwise_op("abs", 1, "Return the absolute value of ``value``.")
sign = elementwise_op(
    "sign", 1, "Return 1, -1 or 0 by the sign of ``value``; ``nan`` stays ``nan``."
)
floor = elementwise_op("floor", 1, "Return the largest integer not above ``value``.")
ceil = elementwise_op("ceil", 1, "Return the smallest integer not below ``value``.")
isnan = elementwise_op("isnan", 1, "Return whether ``value`` is ``nan``.")
isinf = elementwise_op("isinf", 1, "Return whether ``value`` is infinite.")
isfinite = elementwise_op("isfinite", 1, "Return whether ``value`` is finite.")
logical_not = elementwise_op(
    "logical_not", 1, "Return whether the condition does not hold; use it instead of ``not``."
)
atan2 = elementwise_op("atan2", 2, "Return the angle in radians of the point ``(x, y)``.")
maximum = elementwise_op(
    "maximum",
    2,
    "Return the larger of two values like ``max(left, right)``; use it instead of ``max``.",
)
minimum = elementwise_op(
    "minimum",
    2,
    "Return the smaller of two values like ``min(left, right)``; use it instead of ``min``.",
)
logical_or = elementwise_op(
    "logical_or", 2, "Return whether either condition holds; use it instead of ``or``."
)
round = elementwise_op(
    "round",
    2,
    "Return ``value`` rounded to ``digits`` decimals like Python's ``round``, ties to even.",
)
clip = elementwise_op(
    "clip", 3, "Return ``value`` limited to ``[low, high]``; ``nan`` stays ``nan``."
)
identity = elementwise_op(
    "identity",
    1,
    "Return ``value`` unchanged; a trace uses it to guard a value a function passes through.",
)
