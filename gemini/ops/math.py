"""Arithmetic ops and vector indexing; ``truediv``, ``pow``, ``mod`` and ``floordiv`` never raise.

Physics code reaches these through the Python operators of traced values and constants; the
functions below are the same ops for explicit calls.
"""

from gemini.ops.dispatch import dispatch, elementwise_op
from gemini.ops.registry import register

register("getitem", "index", 2)

add = elementwise_op("add", 2, "Return ``left + right``.")
sub = elementwise_op("sub", 2, "Return ``left - right``.")
mul = elementwise_op("mul", 2, "Return ``left * right``.")
truediv = elementwise_op("truediv", 2, "Return ``left / right``.")
pow = elementwise_op("pow", 2, "Return ``base ** exponent``.")
mod = elementwise_op(
    "mod", 2, "Return ``left % right``; a zero divisor gives ``nan`` instead of raising."
)
floordiv = elementwise_op(
    "floordiv",
    2,
    "Return ``left // right``; a zero divisor gives ``inf`` or ``nan`` instead of raising.",
)
neg = elementwise_op("neg", 1, "Return ``-value``.")


def getitem(value, index):
    """Return item ``index`` of a vector value, such as one curve coefficient."""
    return dispatch("getitem", value, index)
