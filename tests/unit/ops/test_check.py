"""``check`` raises the given error with the formatted message, or records a check node."""

import numpy as np
import pytest

from gemini import ops
from gemini.errors import PhysicsError
from gemini.ops import Constant, Symbolic

MESSAGE = "{path}: flow = {flow} m3/s; reverse flow is unsupported"


def test_scalar_check_raises_the_message_of_the_former_f_string():
    """The message equals the f-string it replaces; a passing check returns nothing."""
    flow = -0.25
    assert ops.check(flow < 0, PhysicsError, MESSAGE, path="esp", flow=flow) is None
    with pytest.raises(PhysicsError) as raised:
        ops.check(flow >= 0, PhysicsError, MESSAGE, path="esp", flow=flow)
    assert str(raised.value) == f"esp: flow = {flow} m3/s; reverse flow is unsupported"


def test_array_check_raises_for_the_first_failing_row():
    """On arrays the first failing row fills the message; constants give their value."""
    flow = np.array([0.1, -0.5, -0.7])
    limit = Constant("LIMIT", 0, "m3/s", "lowest flow")
    with pytest.raises(PhysicsError, match=r"^esp: flow = -0.5 m3/s"):
        ops.check(flow >= 0, PhysicsError, MESSAGE + " {limit}", path="esp", flow=flow, limit=limit)


def test_traced_check_is_recorded_with_its_attributes():
    """A symbolic value records one ``check`` op with the error, message and values."""
    recorded = []

    class Recorder(Symbolic):
        def record(self, definition, operands, attributes=None):
            recorded.append((definition.name, operands, attributes))

    flow = Recorder()
    assert ops.check(True, PhysicsError, MESSAGE, path="esp", flow=flow) is None
    name, operands, attributes = recorded[0]
    assert (name, operands, attributes["error"]) == ("check", (True,), PhysicsError)
    assert attributes["values"] == {"path": "esp", "flow": flow}


def test_check_numbers_rejects_nan_with_the_name_of_the_value():
    """A NaN value raises ``PhysicsError`` naming the function and the value; others pass."""
    assert ops.check_numbers("lmtd", dt1=1.0, dt2=2.0) is None
    with pytest.raises(PhysicsError, match=r"^lmtd: dt2 = nan; expected a number$"):
        ops.check_numbers("lmtd", dt1=1.0, dt2=float("nan"))


def test_check_numbers_on_arrays_names_the_first_failing_row():
    """On arrays the failing value of the first NaN row is the one reported."""
    values = np.array([1.0, np.nan, np.nan])
    with pytest.raises(PhysicsError, match=r"^ntu: ua = nan; expected a number$"):
        ops.check_numbers("ntu", ua=values)
