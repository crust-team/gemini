"""The Python backend applies plain operators; unselected branches are safe to evaluate."""

import math
import warnings

import numpy as np

from gemini.backends.python import PythonBackend

BACKEND = PythonBackend()


def test_operators_keep_float32_scalars():
    """Float32 NumPy scalars keep their dtype under the plain operators."""
    value = np.float32(1.5)
    assert BACKEND.mul(value, 2.0).dtype == np.float32
    assert BACKEND.truediv(value, 3.0) == value / 3.0
    assert BACKEND.pow(2.0, 3) == 8.0 and BACKEND.neg(2.0) == -2.0
    assert BACKEND.add(1, 2) == 3 and BACKEND.sub(1, 2) == -1


def test_comparisons_logic_and_indexing():
    """Comparisons give bools, ``logical_and`` both, ``getitem`` one item."""
    assert BACKEND.lt(1, 2) and BACKEND.le(2, 2) and BACKEND.gt(3, 2) and BACKEND.ge(2, 2)
    assert BACKEND.eq(1, 1) and BACKEND.ne(1, 2)
    assert BACKEND.logical_and(True, False) is False
    assert BACKEND.getitem([4, 5], 1) == 5


def test_where_returns_the_selected_value_and_check_gives_codes():
    """``where`` returns the selected branch unchanged, ``None`` included."""
    assert BACKEND.where(True, 0.0, 1.0) == 0.0 and BACKEND.where(False, 0.0, 2.0) == 2.0
    assert BACKEND.where(True, None, 1.0) is None
    assert BACKEND.check(True, 3) == 0 and BACKEND.check(False, 3) == 3


def test_division_and_power_of_an_unselected_branch_never_raise_or_warn():
    """Invalid operands give ``inf`` or ``nan`` as NumPy does, silently, floats and float32."""
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert BACKEND.truediv(1.0, 0.0) == math.inf and BACKEND.truediv(-1, 0.0) == -math.inf
        assert BACKEND.truediv(1.0, -0.0) == -math.inf and math.isnan(BACKEND.truediv(0.0, 0.0))
        quotient = BACKEND.truediv(np.float32(1), np.float32(0))
        assert quotient == math.inf and quotient.dtype == np.float32
        assert BACKEND.pow(0.0, -1) == math.inf and BACKEND.pow(0, -2) == math.inf
        assert math.isnan(BACKEND.pow(-8.0, 0.5)) and BACKEND.pow(10.0, 400) == math.inf
        assert BACKEND.pow(-10.0, 401) == -math.inf
        assert math.isnan(BACKEND.pow(np.float32(-8), np.float32(0.5)))
        assert BACKEND.pow(np.float32(0), np.float32(-1)) == math.inf


def test_selected_branch_values_are_unchanged():
    """Valid operands give exactly what the plain operators give, integers included."""
    assert BACKEND.truediv(7, 2) == 3.5 and BACKEND.pow(2, 10) == 1024
    assert type(BACKEND.pow(2, 10)) is int and BACKEND.pow(2.0, -1) == 0.5
    assert BACKEND.pow(-8.0, 3) == -512.0
