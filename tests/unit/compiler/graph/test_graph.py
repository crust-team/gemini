"""Graphs record ops, lift constants to named inputs and attach checks to traced values."""

import numpy as np
import pytest

from gemini import ops
from gemini.compiler.graph import Graph
from gemini.compiler.graph.errors import TraceError
from gemini.errors import PhysicsError
from gemini.ops import Constant

LIMIT = Constant("LIMIT", 5.0, "Pa", "test limit")


def test_ops_on_inputs_become_nodes_and_constants_one_named_input():
    """Every op is one node; a constant used twice is one input named after it."""
    graph = Graph("test")
    pressure = graph.input("p", "inlet", "Pa")
    rise = pressure * LIMIT + LIMIT
    graph.output("outputs.rise", rise)
    assert [node.op for node in graph.nodes] == ["input", "input", "mul", "add"]
    assert graph.by_role("constant") == {"LIMIT": graph.inputs["LIMIT"]}
    assert graph.constants == {"LIMIT": LIMIT}
    assert graph.outputs["outputs.rise"] is rise.node
    assert (
        "%1<LIMIT> constant [Pa]" in graph.describe() and "add(%2, %1<LIMIT>)" in graph.describe()
    )


def test_a_check_guards_the_results_of_its_physics_function_not_its_named_values():
    """A check gets the next code; the values it names only fill the message."""
    graph = Graph("test")
    pressure = graph.input("p", "inlet", "Pa")
    flow = graph.input("flow", "inlet", "m3/s")

    @ops.physics
    def checked(rate, head):
        ops.check(rate >= 0, PhysicsError, "flow = {flow}", flow=rate)
        ops.check(head >= 0, PhysicsError, "negative pressure")
        return rate * 2.0, head

    with ops.scope.tracing(graph):
        doubled, passed = checked(flow, pressure)
    first, second = graph.checks
    assert (first.code, second.code) == (1, 2)
    assert flow.node.guards == [] and pressure.node.guards == []
    assert doubled.node.guards == [first, second]
    assert passed.node.op == "identity" and passed.node.guards == [first, second]
    assert graph.unframed == []
    assert "code 1: PhysicsError" in graph.describe()


def test_a_check_outside_a_physics_function_is_unframed_and_a_result_free_one_moves_up():
    """Keep an inline check for the tracer; a result-free function hands its checks upward."""
    graph = Graph("test")
    flow = graph.input("flow", "inlet")
    ops.check(flow >= 0, PhysicsError, "inline")

    @ops.physics
    def inner(value):
        ops.check(value >= 0, PhysicsError, "inner")
        return 1.0

    @ops.physics
    def outer(value):
        inner(value)
        return value + 1.0

    with ops.scope.tracing(graph):
        result = outer(flow)
    inline, nested = graph.checks
    assert graph.unframed == [inline] and result.node.guards == [nested]


def test_operands_that_are_not_numbers_cannot_be_traced():
    """Text, other graphs' values and None are refused."""
    graph, other = Graph("test"), Graph("other")
    value = graph.input("x", "inlet")
    with pytest.raises(TraceError, match="operand 'a' of type str"):
        value + "a"
    with pytest.raises(TraceError, match="another graph"):
        value + other.input("y", "inlet")


def test_none_and_fixed_tables_are_literals():
    """``None`` stays a literal; a list of numbers becomes a tuple; traced items are refused."""
    graph = Graph("test")
    x = graph.input("x", "inlet")
    assert ops.where(x > 0, None, x).node.operands[1] is None
    assert ops.interp(x, [0, 1], np.array([2.0, 3.0])).node.operands[1:] == (
        (0.0, 1.0),
        (2.0, 3.0),
    )
    with pytest.raises(TraceError):
        ops.interp(x, [x, 1.0], [2.0, 3.0])


def test_rollback_drops_nodes_inputs_constants_checks_and_their_guards():
    """Everything recorded after a mark disappears, guards included."""
    graph = Graph("test")
    pressure = graph.input("p", "inlet", "Pa")
    kept = pressure + 1.0
    mark = graph.mark()
    extra = graph.input("extra", "control")
    dropped = kept * LIMIT + extra
    graph.open_frame()
    ops.check(dropped > 0, PhysicsError, "{value}", value=kept)
    graph.close_frame(dropped, mark[0])
    assert dropped.node.guards and len(graph.checks) == 1
    graph.rollback(mark)
    assert [node.op for node in graph.nodes] == ["input", "add"]
    assert list(graph.inputs) == ["p"] and graph.constants == {} and graph.checks == []
    assert kept.node.guards == []
    assert graph.mark() == mark


def test_a_list_of_traced_values_is_a_vector_output():
    """Each item is its own output; the graph remembers the length under the list's name."""
    graph = Graph("test")
    pressure = graph.input("p", "inlet", "Pa")
    graph.output("outputs.profile", [pressure, pressure + 1.0, 5.0])
    assert graph.vectors == {"outputs.profile": 3}
    assert list(graph.outputs) == ["outputs.profile[0]", "outputs.profile[1]", "outputs.profile[2]"]
    assert graph.outputs["outputs.profile[2]"] == 5.0


def test_a_concrete_zero_dimensional_array_is_a_literal_number():
    """A backend forced to NumPy gives ``ops`` on constants 0-d arrays; they stay literals."""
    graph = Graph("test")
    x = graph.input("x", "inlet")
    assert (x + np.array(2.5)).node.operands[1] == 2.5
    assert (x > np.array(True)).node.operands[1] is True
