"""The interpreter evaluates a graph on a backend and raises only errors that reach outputs."""

import numpy as np
import pytest

from gemini import ops
from gemini.compiler.graph import Graph, Interpreter
from gemini.errors import PhysicsError, ValidationError
from gemini.ops import kernels
from tests.fixtures.errors import raises
from tests.fixtures.graph_run import graph_outputs


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
        ops.check(value > -2, PhysicsError, "test: y = {y}; expected y > -2", y=value)
        return value

    with ops.scope.tracing(graph):
        graph.output("outputs.y", ops.where(x > 0, x / 2, risky(x)))
    return graph


def test_check_in_the_unselected_branch_does_not_raise():
    """Rows where ``where`` takes the safe branch ignore the risky branch's check."""
    graph = _branch_graph()
    values = graph_outputs(graph, {"x": np.array([3.0, -0.5])})
    assert values["outputs.y"].tolist() == [1.5, -1.0]
    assert graph_outputs(graph, {"x": np.array([2.0, 4.0, -0.5])})


def test_check_in_the_selected_branch_raises_its_class_message_and_line():
    """The first failing selected row raises the error of the untraced path."""
    graph = _branch_graph()
    with pytest.raises(PhysicsError, match=r"^test: y = -4.0") as raised:
        graph_outputs(graph, {"x": np.array([5.0, -2.0, -3.0])})
    assert str(raised.value) == "test: y = -4.0; expected y > -2"
    assert "test_interpreter.py" in raised.value.__notes__[0]


def test_python_backend_runs_one_row_like_numpy():
    """Scalar feeds give the same values on the Python backend."""
    graph = _branch_graph()
    assert graph_outputs(graph, {"x": -0.5}, "python")["outputs.y"] == -1.0
    with pytest.raises(PhysicsError):
        graph_outputs(graph, {"x": -2.0}, "python")


def test_missing_inputs_raise_call_errors():
    """Every graph input needs a value."""
    with raises(ValidationError, "invalid_call", match="without a value: \\['x'\\]"):
        graph_outputs(_branch_graph(), {})


def test_reached_marks_the_failing_rows_instead_of_raising():
    """The codes hold the rows whose error reaches an output; none failing gives ``None``."""
    graph = _branch_graph()
    interpreter = Interpreter(graph, kernels.get("numpy"))
    values, errors = interpreter.execute({"x": np.array([5.0, -2.0, -3.0, 1.0])})
    assert (interpreter.reached(errors) != 0).tolist() == [False, True, True, False]
    assert values[graph.outputs["outputs.y"]][0] == 2.5
    values, errors = interpreter.execute({"x": np.array([5.0, 1.0])})
    assert interpreter.reached(errors) is None
