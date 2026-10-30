"""Dispatch evaluates concrete operands on a backend and records symbolic ones."""

import numpy as np

from gemini.ops import Constant, Symbolic, dispatch

FREQUENCY = Constant("F", 60, "Hz", "reference frequency")


class Recorder(Symbolic):
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
