"""Proxies record ops and refuse what needs a number during a trace."""

import numpy as np
import pytest

from gemini.errors import TraceError
from gemini.graph import Graph


@pytest.fixture
def graph():
    """Return an empty graph."""
    return Graph("test")


def test_operators_record_ops(graph):
    """Arithmetic, comparisons, ``&`` and indexing record their op."""
    x = graph.input("x", "inlet")
    vector = graph.input("v", "parameter", shape=(2,))
    values = [x + 1, 1 + x, x - 1, 1 - x, x * 2, 2 * x, x / 2, 2 / x, x**2, 2**x, -x]
    values += [x < 1, x <= 1, x > 1, x >= 1, x == 1, x != 1, (x > 0) & (x < 1), vector[1]]
    assert [value.node.op for value in values] == [
        "add",
        "add",
        "sub",
        "sub",
        "mul",
        "mul",
        "truediv",
        "truediv",
        "pow",
        "pow",
        "neg",
        "lt",
        "le",
        "gt",
        "ge",
        "eq",
        "ne",
        "logical_and",
        "getitem",
    ]
    assert len(vector) == 2 and [item.node.op for item in vector] == ["getitem", "getitem"]
    assert repr(x) == "Proxy(%0<x>)" and len({x, x}) == 1


@pytest.mark.parametrize(
    "use, what",
    [
        (bool, "a truth value"),
        (float, "float()"),
        (int, "int()"),
        (lambda value: f"{value}", "string formatting"),
        (np.asarray, "a NumPy conversion"),
        (lambda value: [1, 2][value], "an index"),
        (len, "len()"),
    ],
)
def test_untraceable_uses_raise_trace_errors(graph, use, what):
    """Control flow and conversions name what failed and suggest the ops."""
    with pytest.raises(TraceError, match=f"{what}.*use gemini.ops.where"):
        use(graph.input("x", "inlet"))


def test_logical_operators_record_their_ops():
    """``&``, ``|`` and ``~`` on traced conditions record the logical ops on either side."""
    graph = Graph("test")
    x = graph.input("x", "inlet")
    records = {"and": True & (x > 0), "or": True | (x > 0), "not": ~(x > 0)}
    assert records["and"].node.op == "logical_and" and records["and"].node.operands[0] is True
    assert records["or"].node.op == "logical_or" and records["or"].node.operands[0] is True
    assert records["not"].node.op == "logical_not"
