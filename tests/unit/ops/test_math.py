"""Arithmetic op functions match the Python operators on scalars and arrays."""

import numpy as np

from gemini import ops


def test_arithmetic_functions():
    """Each function is its operator."""
    assert ops.add(1.0, 2.0) == 3.0 and ops.sub(1.0, 2.0) == -1.0
    assert ops.mul(2.0, 3.0) == 6.0 and ops.truediv(1.0, 4.0) == 0.25
    assert ops.pow(2.0, 3) == 8.0 and ops.neg(2.0) == -2.0
    assert ops.mul(np.array([1.0, 2.0]), 2).tolist() == [2.0, 4.0]


def test_getitem_selects_one_coefficient():
    """``getitem`` selects one item of a vector."""
    assert ops.getitem([3.0, 4.0], 1) == 4.0
