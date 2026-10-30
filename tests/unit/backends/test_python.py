"""The Python backend applies plain operators and evaluates only the selected branch."""

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


def test_where_calls_only_the_selected_branch_and_check_gives_codes():
    """An unselected callable branch that would divide by zero is never called."""
    assert BACKEND.where(True, 0.0, lambda: 1 / 0) == 0.0
    assert BACKEND.where(False, lambda: 1 / 0, 2.0) == 2.0
    assert BACKEND.check(True, 3) == 0 and BACKEND.check(False, 3) == 3
