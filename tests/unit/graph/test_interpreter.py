"""The interpreter evaluates a graph on a backend and raises only errors that reach outputs."""

import numpy as np
import pytest

from gemini import backends, ops
from gemini.errors import CallError, PhysicsRangeError
from gemini.graph import Graph, Interpreter


def _branch_graph():
    """Return ``where(x > 0, x / 2, risky())``; the risky branch checks its value ``2 x > -2``.

    The check is in a physics function, so its error guards that function's result and travels
    with the branch that uses it only.
    """
    graph = Graph("test")
    x = graph.input("x", "inlet")

    @ops.physics
    def risky(point):
        value = point * 2
        ops.check(value > -2, PhysicsRangeError, "test: y = {y}; expected y > -2", y=value)
        return value

    with ops.scope.tracing(graph):
        graph.output("outputs.y", ops.where(x > 0, x / 2, risky(x)))
    return graph


def test_check_in_the_unselected_branch_does_not_raise():
    """Rows where ``where`` takes the safe branch ignore the risky branch's check."""
    graph = _branch_graph()
    values = Interpreter(graph, backends.get("numpy")).run({"x": np.array([3.0, -0.5])})
    assert values["outputs.y"].tolist() == [1.5, -1.0]
    assert Interpreter(graph, backends.get("numpy")).run({"x": np.array([2.0, 4.0, -0.5])})


def test_check_in_the_selected_branch_raises_its_class_message_and_line():
    """The first failing selected row raises the error of the untraced path."""
    graph = _branch_graph()
    with pytest.raises(PhysicsRangeError, match=r"^test: y = -4.0") as raised:
        Interpreter(graph, backends.get("numpy")).run({"x": np.array([5.0, -2.0, -3.0])})
    assert str(raised.value) == "test: y = -4.0; expected y > -2"
    assert "test_interpreter.py" in raised.value.__notes__[0]


def test_python_backend_runs_one_row_like_numpy():
    """Scalar feeds give the same values on the Python backend."""
    graph = _branch_graph()
    assert Interpreter(graph, backends.get("python")).run({"x": -0.5})["outputs.y"] == -1.0
    with pytest.raises(PhysicsRangeError):
        Interpreter(graph, backends.get("python")).run({"x": -2.0})


def test_missing_inputs_raise_call_errors():
    """Every graph input needs a value."""
    with pytest.raises(CallError, match="without a value: \\['x'\\]"):
        Interpreter(_branch_graph(), backends.get("numpy")).run({})


def test_reached_marks_the_failing_rows_instead_of_raising():
    """The codes hold the rows whose error reaches an output; none failing gives ``None``."""
    graph = _branch_graph()
    interpreter = Interpreter(graph, backends.get("numpy"))
    values, errors = interpreter.execute({"x": np.array([5.0, -2.0, -3.0, 1.0])})
    assert (interpreter.reached(errors) != 0).tolist() == [False, True, True, False]
    assert values[graph.outputs["outputs.y"]][0] == 2.5
    values, errors = interpreter.execute({"x": np.array([5.0, 1.0])})
    assert interpreter.reached(errors) is None
