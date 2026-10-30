"""Dispatch evaluates concrete operands on a backend and records symbolic ones."""

import warnings

import numpy as np
import pytest

from gemini import backends, ops
from gemini.ops import Constant, Operators, Symbolic, dispatch

FREQUENCY = Constant("F", 60, "Hz", "reference frequency")


class Recorder(Symbolic, Operators):
    """Symbolic operand that returns what it was asked to record."""

    def record(self, definition, operands, attributes=None):
        """Return the op name and operands."""
        return definition.name, operands


def test_constants_act_as_their_float_including_float32_promotion():
    """A constant is its float in arithmetic; NumPy float32 stays float32 as with a float."""
    value = np.float32(55.5)
    assert type(value / FREQUENCY) is np.float32 and value / FREQUENCY == value / 60.0
    assert 30 / FREQUENCY == 0.5 and FREQUENCY * 2 == 120.0 and FREQUENCY - 10 == 50.0
    assert FREQUENCY + 1 == 61.0 and 1 + FREQUENCY == 61.0 and 70 - FREQUENCY == 10.0
    assert -FREQUENCY == -60.0 and FREQUENCY**2 == 3600.0 and 2**FREQUENCY == 2.0**60
    assert (np.arange(3.0) * FREQUENCY).tolist() == [0.0, 60.0, 120.0]
    assert FREQUENCY > 50 and FREQUENCY >= 60 and FREQUENCY < 70 and FREQUENCY <= 60
    assert float(FREQUENCY) == 60.0 and f"{FREQUENCY:.1f}" == "60.0"
    assert repr(FREQUENCY) == "Constant(F=60.0 Hz)"


def test_symbolic_operands_are_recorded_not_evaluated():
    """An op with a symbolic operand goes to that operand's ``record``."""
    symbolic = Recorder()
    assert dispatch("mul", 2.0, symbolic) == ("mul", (2.0, symbolic))
    assert FREQUENCY / symbolic == ("truediv", (FREQUENCY, symbolic))


def test_constant_is_not_a_float_and_computes_like_its_float():
    """Operators compute on ``value`` as Python does, so a zero divisor raises like a float."""
    assert not isinstance(FREQUENCY, float)
    assert FREQUENCY + 1 == 61.0 and 2 * FREQUENCY == 120.0 and FREQUENCY // 7 == 8.0
    assert FREQUENCY % 7 == 4.0 and 100 % FREQUENCY == 40.0 and abs(-FREQUENCY) == 60.0
    assert FREQUENCY / FREQUENCY == 1.0 and FREQUENCY < FREQUENCY + 1 and 59 < FREQUENCY
    assert 10 < FREQUENCY and FREQUENCY >= 60 and FREQUENCY > 59.5
    with pytest.raises(ZeroDivisionError):
        FREQUENCY / 0.0
    assert ops.truediv(FREQUENCY, 0.0) == float("inf")
    symbolic = Recorder()
    assert FREQUENCY * symbolic == ("mul", (FREQUENCY, symbolic))
    assert symbolic * FREQUENCY == ("mul", (symbolic, FREQUENCY))
    assert 1 - FREQUENCY == -59.0 and 1 + FREQUENCY == 61.0


def test_plain_scalars_skip_dispatch_and_settings_still_force_a_backend():
    """Floats go straight to the Python backend; a backend setting or an array still dispatches."""
    assert type(ops.log(2.0)) is float and ops.where(True, 1.0, 2.0) == 1.0
    with backends.settings("numpy"):
        assert type(ops.log(2.0)) is np.float64
        assert ops.where(True, 1.0, 2.0) == 1.0
        assert type(ops.maximum(1.0, 2.0)) is np.float64
    assert type(ops.log(2.0)) is float
    assert ops.log(np.array([1.0, np.e])).tolist() == [0.0, 1.0]
    assert type(ops.log(np.float32(2.0))) is float
    constant = Constant("c", 2.0, "-", "two")
    assert type(ops.maximum(constant, 1.0)) is float
    assert type(ops.where(True, constant, 1.0)) is float


def test_numpy_float64_rows_take_the_fast_path_silently():
    """Values taken from a dataset row (float64, bool_) divide and select without warnings."""
    row = np.array([1.0, 0.0])
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        quotient = ops.truediv(row[0], row[1])
        assert quotient == float("inf") and ops.truediv(row[0], 4.0) == 0.25
        assert type(ops.truediv(row[0], 4.0)) is np.float64
        assert ops.where(row[0] > row[1], row[0], None) == 1.0
        assert ops.where(row[1] > row[0], row[0], None) is None
        assert ops.pow(row[1], -1.0) == float("inf")
