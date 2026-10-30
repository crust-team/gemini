"""``Failed``: a failed check travels with a value in an eager scope and ``where`` can drop it."""

import numpy as np
import pytest

from gemini import ops
from gemini.errors import PhysicsRangeError
from gemini.ops import Constant, Failed

MESSAGE = "{path}: x = {x} m; expected x >= 0"
SCALE = Constant("SCALE", 2.0, "-", "a test constant")


@ops.physics
def checked(x):
    """Double ``x``, which must not be negative."""
    ops.check(x >= 0, PhysicsRangeError, MESSAGE, path="pipe", x=x)
    return x * 2.0


@ops.physics
def inner(x):
    """Call the checked function from a nested physics function."""
    return checked(x) + 1.0


def root(low, high, shift):
    """Residual of a bracketed solve."""
    return low - high - shift


@ops.physics
def stopped_or_checked(x, stopped):
    """Return zero when stopped, else the checked value: one version for every case."""
    return ops.where(stopped, 0.0, checked(x))


@ops.physics
def checked_condition(x):
    """Branch on a checked value."""
    return ops.where(checked(x) > 1.0, 1.0, 2.0)


def test_outside_a_scope_the_check_raises_the_real_error():
    """The caller of a physics function sees the check's class and exact message."""
    assert checked(1.5) == 3.0
    with pytest.raises(PhysicsRangeError) as raised:
        checked(-1.0)
    assert type(raised.value) is PhysicsRangeError
    assert str(raised.value) == "pipe: x = -1.0 m; expected x >= 0"
    with pytest.raises(PhysicsRangeError, match="expected x >= 0"):
        inner(-1.0)


def test_where_drops_an_error_of_the_unselected_branch_and_keeps_the_selected_one():
    """A concrete condition selects a branch and its error, as the graph's error codes do."""
    assert stopped_or_checked(-1.0, True) == 0.0
    assert stopped_or_checked(2.0, False) == 4.0
    with pytest.raises(PhysicsRangeError, match="x = -1.0 m"):
        stopped_or_checked(-1.0, False)
    with pytest.raises(PhysicsRangeError, match="x = -1.0 m"):
        checked_condition(-1.0)
    assert stopped_or_checked(np.float64(-1.0), np.bool_(True)) == 0.0


def test_a_failed_value_carries_through_every_kind_of_op():
    """Arithmetic with floats, NumPy scalars and constants, sum, abs, every arity and a solver."""
    failure = Failed(PhysicsRangeError("boom"))
    carried = [
        failure + 1.0,
        1.0 - failure,
        np.float64(2.0) * failure,
        failure / np.float64(0.0),
        SCALE + failure,
        failure * SCALE,
        sum([1.0, failure, 2.0]),
        abs(failure),
        -failure,
        failure > 1.0,
        2.0 < failure,
        failure == 0,
        ops.sqrt(failure),
        ops.maximum(1.0, failure),
        ops.clip(failure, 0.0, 1.0),
        ops.logical_and(True, failure),
        failure & True,
        ops.truediv(1.0, failure),
        ops.brentq(root, 0.0, 1.0, args=(failure,)),
        ops.newton(root, failure, root, args=(1.0, 1.0)),
    ]
    assert all(value is failure for value in carried)
    assert ops.where(False, failure, 3.0) == 3.0 and ops.where(True, failure, 3.0) is failure
    assert ops.where(failure, 1.0, 2.0) is failure


def test_a_failed_condition_stays_failed_and_a_check_on_it_does_nothing():
    """Only a concrete condition drops an error; the first failure is the one a value carries."""
    first = Failed(PhysicsRangeError("first"))
    assert ops.where(first, 1.0, 2.0) is first
    assert ops.check(first, ValueError, "second") is None
    assert ops.check(False, ValueError, "second {x}", x=first) is None


def test_using_a_failed_as_a_plain_number_raises_its_error():
    """``bool``, ``float``, ``int`` and ``format`` surface the error; ``repr`` does not."""
    error = PhysicsRangeError("boom")
    failure = Failed(error)
    for convert in (bool, float, int, format):
        with pytest.raises(PhysicsRangeError, match="boom"):
            convert(failure)
    assert repr(failure) == "Failed(PhysicsRangeError: boom)"


def test_leaving_the_outermost_scope_with_a_failed_anywhere_raises():
    """A failure inside a tuple, dict or list result raises its error."""

    @ops.physics
    def holder(x, kind):
        value = inner(x)
        return {"tuple": (1.0, value), "list": [value], "dict": {"a": value}}[kind]

    for kind in ("tuple", "list", "dict"):
        with pytest.raises(PhysicsRangeError, match="x = -1.0 m"):
            holder(-1.0, kind)


def test_a_check_on_an_eager_array_raises_at_once_for_the_first_failing_row():
    """Arrays are never turned into a ``Failed``: the first failing row raises, with its values."""
    values = np.array([1.0, -2.0, -3.0])
    with pytest.raises(PhysicsRangeError, match="x = -2.0 m"):
        checked(values)
    with pytest.raises(PhysicsRangeError, match="x = -2.0 m"):
        inner(values)
