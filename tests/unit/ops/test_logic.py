"""Comparisons, ``logical_and`` and ``where`` on scalars, arrays and traced conditions."""

import numpy as np

from gemini import ops
from gemini.ops import Symbolic

X = np.array([0.0, 2.0])


def test_comparisons_and_logical_and():
    """Comparison functions match their operators; ``logical_and`` replaces chained ``<=``."""
    assert ops.lt(1, 2) and ops.le(2, 2) and ops.gt(3, 2) and ops.ge(2, 2)
    assert ops.eq(1, 1) and ops.ne(1, 2)
    assert ops.logical_and(1 <= 2, 2 <= 3) is True
    assert ops.logical_and(X >= 0, X <= 1).tolist() == [True, False]


def test_where_on_scalars_evaluates_only_the_selected_callable():
    """A scalar condition never calls the branch that would divide by zero."""
    assert ops.where(0.0 < 0.1, 0.0, lambda: 1 / 0.0) == 0.0
    assert ops.where(X < 1, 0.0, lambda: 1 / X).tolist() == [0.0, 0.5]


def test_traced_condition_calls_both_branches_before_recording():
    """A symbolic condition records ``where`` with both branch values."""

    class Recorder(Symbolic):
        def record(self, definition, operands, attributes=None):
            return definition.name, operands

    condition = Recorder()
    assert ops.where(condition, lambda: 1, 2) == ("where", (condition, 1, 2))
