"""``RowView`` reads one row of a graph's values; ``row_error`` words the failure."""

import numpy as np

from gemini.compiler.graph import GraphCache
from gemini.compiler.graph.failures import RowView, row_error
from gemini.compiler.graph.interpreter import Interpreter
from gemini.errors import PhysicsError
from gemini.ops import kernels


def test_row_view_reads_rows_parameters_and_literals(gain):
    """A column gives its item, a parameter its original value, a literal itself."""
    graph = GraphCache().graph(gain, {"fluid_in": gain.fluid})
    feeds = {
        "fluid_in.m_dot": np.ones(2),
        "fluid_in.T": np.full(2, 300.0),
        "fluid_in.p": np.array([1.0, 2.0]),
        "gain": np.array([1.0, -1.0]),
        "scale": np.asarray(3),
        "REFERENCE": 2.0,
    }
    values, errors = Interpreter(graph, kernels.get("numpy")).execute(feeds)
    view = RowView(values, 1, feeds)
    assert view.value(graph.inputs["fluid_in.p"]) == 2.0
    assert view.value(graph.inputs["scale"]) == 3
    assert view.value(4.5) == 4.5 and view.value([graph.inputs["gain"], 1.0]) == [-1.0, 1.0]


def test_row_error_fills_the_message_of_the_row(gain):
    """The check's class and message with the values of the failing row."""
    graph = GraphCache().graph(gain, {"fluid_in": gain.fluid})
    feeds = {
        "fluid_in.m_dot": np.ones(2),
        "fluid_in.T": np.full(2, 300.0),
        "fluid_in.p": np.ones(2),
        "gain": np.array([1.0, -1.0]),
        "scale": np.asarray(3.0),
        "REFERENCE": 2.0,
    }
    interpreter = Interpreter(graph, kernels.get("numpy"))
    values, errors = interpreter.execute(feeds)
    codes = interpreter.reached(errors)
    error = row_error(graph.checks[int(codes[1]) - 1], RowView(values, 1, feeds))
    assert isinstance(error, PhysicsError) and "gain = -1.0" in str(error)
