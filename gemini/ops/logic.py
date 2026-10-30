"""Comparison ops, ``logical_and`` and ``where``, the branch choice of traced physics.

``where(condition, if_true, if_false)`` replaces a value-dependent ``if``: write
``where(re < 2300, 64 / re, turbulent(re))`` instead of an ``if`` statement. Both branches are
plain values and are always evaluated. A branch that can be invalid where it is not selected
uses ``ops.truediv`` or ``ops.pow`` rather than ``/`` or ``**``, which give ``inf`` or ``nan``
silently instead of raising on Python floats. A branch may be ``None``: it stays ``None`` on
Python values and is NaN in arrays and graphs.
"""

from gemini.ops.dispatch import elementwise_op

lt = elementwise_op("lt", 2, "Return ``left < right``.")
le = elementwise_op("le", 2, "Return ``left <= right``.")
gt = elementwise_op("gt", 2, "Return ``left > right``.")
ge = elementwise_op("ge", 2, "Return ``left >= right``.")
eq = elementwise_op("eq", 2, "Return ``left == right``.")
ne = elementwise_op("ne", 2, "Return ``left != right``.")
logical_and = elementwise_op(
    "logical_and",
    2,
    "Return whether both conditions hold; use it instead of ``and`` or ``a <= b <= c``.",
)
where = elementwise_op(
    "where", 3, "Return ``if_true`` where ``condition`` holds and ``if_false`` elsewhere."
)
