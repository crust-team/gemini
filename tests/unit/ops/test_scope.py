"""The eager physics scope: silent plain operators, NumPy scalars inside, plain scalars outside."""

import dataclasses
import math

import numpy as np
import pytest

from gemini import backends, ops
from gemini.errors import PhysicsError
from gemini.graph import run_function
from gemini.ops import Constant
from gemini.types.flows import Stream
from gemini.types.fluid import BRINE

LIMIT = Constant("LIMIT", 2.0, "-", "a test constant")


@dataclasses.dataclass(frozen=True)
class Pair:
    """Frozen result fixture."""

    first: float
    second: float


@ops.physics
def divide(numerator, denominator):
    """Divide with the plain operator."""
    return numerator / denominator


@ops.physics
def kinds(*values):
    """Return the exact type names the function received."""
    return tuple(type(value).__name__ for value in values)


@ops.physics
def results(value):
    """Return NumPy scalars in every container the scope unwraps."""
    scalar = value * 2.0
    return {"tuple": (scalar, np.bool_(True)), "list": [scalar], "pair": Pair(scalar, scalar)}


def test_plain_operators_are_silent_and_follow_ieee_in_the_scope():
    """Division by zero, an invalid power and an overflow give inf or nan without warnings."""
    assert divide(1.0, 0.0) == math.inf and divide(-1.0, 0.0) == -math.inf
    assert math.isnan(divide(0.0, 0.0))

    @ops.physics
    def invalid(base):
        return (base**0.5, base * 1e308 * 10.0)

    root, overflow = invalid(-4.0)
    assert math.isnan(root) and overflow == -math.inf


def test_a_nested_call_wraps_its_own_literal_floats():
    """A literal ``0.0`` passed to a nested physics function divides silently."""

    @ops.physics
    def outer(value):
        return divide(value, 0.0) + divide(numerator=value, denominator=0.0)

    assert outer(1.0) == math.inf


def test_only_exact_numbers_are_wrapped_and_results_leave_plain():
    """None, strings and bools pass through; scalars leave as float, bool and containers."""
    assert kinds(1.0, 2, None, "s", True) == ("float64", "int64", "NoneType", "str", "bool")
    value = results(1.5)
    assert type(value["tuple"][0]) is float and type(value["tuple"][1]) is bool
    assert type(value["list"][0]) is float and type(value["pair"].second) is float
    assert repr(value["pair"]) == "Pair(first=3.0, second=3.0)"
    assert type(divide(1.0, 2.0)) is float


def test_arrays_leave_the_scope_unwrapped_and_a_plain_module_scope_restores_the_mode():
    """An array argument never gives ``np.float64`` scalars; a PLAIN entry restores WRAP."""
    assert kinds(1.0, np.ones(2))[0] == "float"
    values = np.ones(2, dtype=np.float32)
    assert (values * ops.physics(lambda x: x)(2.0)).dtype == np.float32
    with ops.scope.Scope() as outer:
        assert outer.wrapping and backends.scope_mode() is backends.WRAP
        with ops.scope.Scope(backends.PLAIN) as inner:
            assert not inner.wrapping and backends.scope_mode() is backends.PLAIN
            assert kinds(1.0) == ("float",)
        assert backends.scope_mode() is backends.WRAP
    assert backends.scope_mode() is None


def test_constant_arithmetic_is_silent_inside_and_raises_outside():
    """``Constant / 0.0`` follows IEEE in the scope and raises like a float outside it."""

    @ops.physics
    def scaled(value):
        return (LIMIT / value, value / LIMIT, LIMIT**value, -LIMIT)

    assert scaled(0.0) == (math.inf, 0.0, 1.0, -2.0)
    with pytest.raises(ZeroDivisionError):
        LIMIT / 0.0
    assert type(LIMIT * np.float32(1.0)) is np.float32


def test_round_uses_python_rounding_for_numpy_scalars():
    """``ops.round`` rounds ``np.float64`` as a ``float``, not with NumPy's rounding."""
    assert ops.round(np.float64(2.675), 2) == round(2.675, 2) == 2.67
    assert type(ops.round(np.float64(2.675), 2)) is float


def test_the_scope_restores_the_mode_and_errstate_after_an_error():
    """A failing function leaves no scope behind."""

    @ops.physics
    def failing(value):
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        failing(1.0)
    assert backends.scope_mode() is None
    with pytest.warns(RuntimeWarning):
        np.float64(1.0) / np.float64(0.0)


def test_integer_arguments_divide_silently_and_stay_integers():
    """An int is an ``np.int64``: ``/`` by zero is silent, it prints and indexes as an int."""

    @ops.physics
    def ratio(left, right):
        ops.check(left >= 0, PhysicsError, "ratio: left = {left}", left=left)
        return [left / right, list(range(right + 2))]

    assert ratio(1, 0) == [math.inf, [0, 1]]
    with pytest.raises(PhysicsError, match="ratio: left = -1$"):
        ratio(-1, 1)


def test_a_stream_of_traced_values_keeps_the_frames_of_nested_functions():
    """A check in a nested function guards its result though the argument hides its proxies."""

    @ops.physics
    def checked(stream):
        ops.check(stream.p > 0, PhysicsError, "checked: p = {p}", p=stream.p)
        return stream.p

    @ops.physics
    def outer(pressure):
        stream = Stream._trusted(m_dot=1.0, T=300.0, p=pressure, fluid=BRINE)
        return ops.where(pressure > 0, checked(stream), 0.0)

    values = run_function(outer, np.array([1.0, -1.0]))
    assert values.tolist() == [1.0, 0.0]


def test_a_zero_dimensional_array_is_a_scalar_for_the_scope():
    """A forced NumPy backend gives 0-d arrays; they must not turn a call into an array call."""
    assert kinds(np.array(1.0), 2.0)[1] == "float64"
