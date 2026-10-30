"""The NumPy backend works on arrays and silences the warnings of unselected branches."""

import warnings

import numpy as np

from gemini.backends.numpy import NumpyBackend

BACKEND = NumpyBackend()
X = np.array([0.0, 1.0, 2.0])


def test_arithmetic_and_comparisons_per_row():
    """Every elementwise op applies row by row."""
    assert BACKEND.add(X, 1).tolist() == [1, 2, 3]
    assert BACKEND.sub(X, 1).tolist() == [-1, 0, 1]
    assert BACKEND.mul(X, 2).tolist() == [0, 2, 4]
    assert BACKEND.pow(X, 2).tolist() == [0, 1, 4]
    assert BACKEND.neg(X).tolist() == [0, -1, -2]
    assert BACKEND.lt(X, 1).tolist() == [True, False, False]
    assert BACKEND.le(X, 1).tolist() == [True, True, False]
    assert BACKEND.gt(X, 1).tolist() == [False, False, True]
    assert BACKEND.ge(X, 1).tolist() == [False, True, True]
    assert BACKEND.eq(X, 1).tolist() == [False, True, False]
    assert BACKEND.ne(X, 1).tolist() == [True, False, True]
    assert BACKEND.logical_and(X > 0, X < 2).tolist() == [False, True, False]


def test_division_by_zero_in_an_unselected_branch_is_silent():
    """Both branches run; the zero division warns nothing and is not selected."""
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        ratio = BACKEND.truediv(1.0, X)
        selected = BACKEND.where(X == 0, 0.0, lambda: 1.0 / X)
    assert np.isinf(ratio[0]) and selected.tolist() == [0.0, 1.0, 0.5]


def test_check_codes_and_vector_indexing_on_the_last_axis():
    """Check codes are zero where the condition holds; vectors index their last axis."""
    assert BACKEND.check(X > 0, 2).tolist() == [2, 0, 0]
    assert BACKEND.getitem([[1, 2], [3, 4]], 1).tolist() == [2, 4]
