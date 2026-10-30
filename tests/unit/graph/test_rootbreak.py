"""A root that cannot be traced is called for real, row by row, with exact result trees."""

import numpy as np
import pytest

import gemini as gm
from gemini import backends
from gemini.errors import PhysicsError
from gemini.graph import GraphCache, evaluate, graph_feeds

from .conftest import Chain, Gain, Opaque, Tank


def _inlets(rows):
    return {
        "inlet": gm.Stream(
            m_dot=np.arange(1.0, rows + 1),
            T=np.full(rows, 300.0),
            p=np.full(rows, 1e5),
            fluid=gm.WATER,
        )
    }


def _evaluate(module, inputs, rows, stepped=False, context=None, backend=None):
    inlets = _inlets(rows)
    graph = GraphCache().graph(module, {"inlet": gm.WATER}, stepped)
    feeds = graph_feeds(graph, module, inlets, inputs)
    with backends.settings(backend=backend):
        return graph, evaluate(graph, feeds, rows, context)


@pytest.mark.parametrize("backend", [None, "python"])
def test_a_composite_root_break_gives_real_trees(backend):
    """Children, outputs and the sum over the leaves are those of direct calls."""
    chain = Chain(Opaque())
    graph, evaluation = _evaluate(chain, {"drive": 1.0}, 3, backend=backend)
    assert graph.root is chain and {node.op for node in graph.nodes} == {"input"}
    assert evaluation.failed.tolist() == [False] * 3
    assert evaluation.result.children.keys() == {"first", "middle", "last"}
    assert evaluation.result.children["middle"].children.keys() == {"meter"}
    row = chain(gm.Stream(m_dot=2.0, T=300.0, p=1e5, fluid=gm.WATER))
    assert evaluation.result.row(1).outputs.electricity == row.outputs.electricity
    assert (
        evaluation.result.row(1).children["last"].outlets.outlet.p
        == row.children["last"].outlets.outlet.p
    )


def test_failed_rows_keep_their_exception_and_are_nan():
    """A row that raises is failed with its own exception; the others are unchanged."""
    module = Gain().update_params(scale=3.0)
    module.register_forward_pre_hook(lambda module, inlets: None)
    _, evaluation = _evaluate(module, {"gain": np.array([1.0, -2.0, 3.0])}, 3)
    assert evaluation.failed.tolist() == [False, True, False]
    assert isinstance(evaluation.error(1), PhysicsError)
    assert "gain = -2.0" in str(evaluation.error(1))
    assert np.isnan(evaluation.result.outputs["rise"][1])
    assert evaluation.result.outputs["rise"][[0, 2]].tolist() == [6.0, 18.0]


def test_controls_are_applied_for_the_call_only():
    """Persisted inputs are put back: persisting is the caller's business."""
    module = Gain().update_params(scale=3.0)
    module.gain = 1.0
    module.register_forward_pre_hook(lambda module, inlets: None)
    _evaluate(module, {"gain": np.array([2.0, 3.0])}, 2)
    assert module._input_value("gain") == 1.0


def test_a_stepped_break_carries_the_states_row_to_row():
    """``Module.step`` runs per row with the context's dt and states; failed rows keep them."""
    tank = Tank()
    context = {"dt": 60.0, "states": None}
    graph, evaluation = _evaluate(tank, {}, 3, stepped=True, context=context)
    assert graph.root is tank and graph.stepped
    assert evaluation.result.outputs["content"].tolist() == [1.0, 3.0, 6.0]
    assert evaluation.states == {"level": 6.0}
    again = {"dt": 60.0, "states": {"level": 6.0}}
    _, resumed = _evaluate(tank, {}, 1, stepped=True, context=again)
    assert resumed.result.outputs["content"].tolist() == [7.0]


def test_an_unstepped_break_calls_a_stateful_module():
    """Not stepped, the module starts from its initial states, as a call does."""
    tank = Tank()
    graph, evaluation = _evaluate(tank, {}, 3)
    assert not graph.stepped and evaluation.states is None
    assert evaluation.result.outputs["content"].tolist() == [1.0, 2.0, 3.0]


def test_every_row_failing_gives_no_result():
    """Without an ok row there is no tree to stack."""
    module = Gain().update_params(scale=3.0)
    module.register_forward_pre_hook(lambda module, inlets: None)
    _, evaluation = _evaluate(module, {"gain": np.array([-1.0, -2.0])}, 2)
    assert evaluation.failed.all() and evaluation.result is None
