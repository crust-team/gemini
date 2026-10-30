"""The runner evaluates arrays in one traced call or falls back to untraced calls."""

import numpy as np
import pytest

import gemini as gm
from gemini.errors import PhysicsRangeError, TraceError
from gemini.graph import GraphCache, Proxy, run
from gemini.utils.hooks import observer

from .conftest import Chain, Gain, Opaque, Stubborn, Switcher, Tank


def _rows(gain, inlet, frequency):
    return [
        gain(
            inlet=gm.Stream(m_dot=1.0, T=inlet.T[row], p=inlet.p[row], fluid=inlet.fluid),
            gain=frequency[row],
        )
        for row in range(3)
    ]


def test_traced_run_matches_untraced_calls(gain, inlet):
    """Every output and outlet field equals the row-by-row results."""
    controls = np.array([0.0, 1.0, 2.0])
    result = run(gain, {"inlet": inlet}, {"gain": controls})
    expected = _rows(gain, inlet, controls)
    assert result.breaks == [] and result.graph is not None
    assert result.outputs["rise"].tolist() == [row.outputs.rise for row in expected]
    assert result.outputs["boost"].tolist() == [row.outputs.boost for row in expected]
    assert result.outlets["outlet"]["p"].tolist() == [row.outlets.outlet.p for row in expected]


def test_graph_break_runs_untraced_with_the_same_results(gain, inlet):
    """A pre-hook breaks the graph; the reason is reported and the values are unchanged."""
    gain.register_forward_pre_hook(lambda module, inlets: None)
    result = run(gain, {"inlet": inlet}, {"gain": 1.0})
    assert result.graph is None and "pre-hooks" in result.breaks[0]
    assert result.outputs["rise"].tolist() == [6.0, 6.0, 6.0]


def test_observer_hooks_are_replayed_per_row(gain, inlet):
    """A reading hook sees every row's values after the traced run.

    It also ran once during the trace, on traced values, which is what classifies it.
    """
    seen = []
    gain.register_forward_hook(lambda module, inlets, outlets: seen.append(module.rise))
    run(gain, {"inlet": inlet}, {"gain": 1.0})
    assert isinstance(seen[0], Proxy) and seen[1:] == [6.0, 6.0, 6.0]


def test_errors_raise_after_the_run(gain, inlet):
    """A negative gain raises the untraced error for its first row."""
    with pytest.raises(PhysicsRangeError, match="gain: gain = -1.0"):
        run(gain, {"inlet": inlet}, {"gain": np.array([1.0, -1.0, -2.0])})


def test_structural_parameter_decides_the_traced_shape(stepper, inlet):
    """A structural count unrolls the loop of the trace; the numeric increment stays an input."""
    cache = GraphCache()
    for steps, increment in ((2, 1.0), (3, 10.0)):
        stepper.update_params(steps=steps, increment=increment)
        result = run(stepper, {"inlet": inlet}, cache=cache)
        assert result.outlets["outlet"]["p"].tolist() == (inlet.p + steps * increment).tolist()
    assert cache.traces == 2


def test_module_without_inlets_takes_its_row_count_from_the_inputs(source):
    """The control array sets the rows; a graph break gives the same values row by row."""
    controls = np.array([1.0, 2.0, 3.0])
    result = run(source, {}, {"rate": controls})
    assert result.outputs["double"].tolist() == [2.0, 4.0, 6.0]
    assert result.outlets["outlet"]["m_dot"].tolist() == [1.0, 2.0, 3.0]
    assert result.outlets["outlet"]["T"].tolist() == [300.0] * 3
    source.register_forward_pre_hook(lambda module, inlets: None)
    assert run(source, {}, {"rate": controls}).outputs["double"].tolist() == [2.0, 4.0, 6.0]


def test_module_without_inlets_or_arrays_has_one_row(source):
    """Scalar inputs and no inlets give a single row."""
    assert run(source, {}, {"rate": 5.0}).outputs["double"].tolist() == [10.0]


def test_marked_hooks_are_never_called_on_traced_values(gain, inlet):
    """Marked pre-hooks and forward hooks only see rows, pre-hooks first, and keep the graph."""
    seen = []
    gain.register_forward_pre_hook(observer(lambda module, inlets: seen.append("pre")))
    gain.register_forward_hook(observer(lambda module, inlets, outlets: seen.append(module.rise)))
    result = run(gain, {"inlet": inlet}, {"gain": 1.0})
    assert result.graph is not None and result.breaks == []
    assert seen == ["pre", 6.0, "pre", 6.0, "pre", 6.0]


def _line_rows(line, inlet, boosts, draws):
    rows = []
    for row in range(3):
        line.second.draw = draws[row]
        stream = gm.Stream(m_dot=1.0, T=inlet.T[row], p=inlet.p[row], fluid=inlet.fluid)
        rows.append(line(inlet=stream, boost=boosts[row]))
    return rows


def test_composite_run_matches_untraced_calls(line, inlet):
    """Output.of, outlet fields, automatic sums, ratios and outlets equal the row-by-row calls."""
    boosts, draws = [1.0, 2.0, 3.0], np.array([2.0, 0.0, 5.0])
    line.first.update_params(scale=0.0)
    result = run(line, {"inlet": inlet}, {"boost": np.array(boosts), "second.draw": draws})
    expected = _line_rows(line, inlet, boosts, draws)
    assert result.graph is not None and result.breaks == []
    for name in ("rise", "pressure", "electricity"):
        assert result.outputs[name].tolist() == [row.outputs[name] for row in expected]
    ratios = [row.outputs.efficiency for row in expected]
    assert ratios[1] is None
    assert np.isnan(result.outputs["efficiency"][1])
    assert result.outputs["efficiency"][[0, 2]].tolist() == [ratios[0], ratios[2]]
    assert result.outlets["outlet"]["p"].tolist() == [row.outlets.outlet.p for row in expected]


def test_composite_child_inputs_come_from_the_tree(line, inlet):
    """A child control not supplied by the root is fed from the child's persisted value."""
    line.second.draw = 4.0
    result = run(line, {"inlet": inlet}, {"boost": 1.0})
    assert result.outputs["electricity"].tolist() == [10.0] * 3


def test_composite_errors_raise_the_child_error(line, inlet):
    """A negative control of a child raises the child's error class and message."""
    with pytest.raises(PhysicsRangeError, match="gain: gain = -1.0"):
        run(line, {"inlet": inlet}, {"boost": np.array([1.0, -1.0, 2.0])})


def _chain_rows(chain, inlet, drives):
    rows = []
    for row in range(3):
        stream = gm.Stream(
            m_dot=inlet.m_dot[row], T=inlet.T[row], p=inlet.p[row], fluid=inlet.fluid
        )
        rows.append(chain(inlet=stream, drive=drives[row]))
    return rows


@pytest.fixture
def chain_inlet():
    """Return a three-row water inlet for the chains."""
    return gm.Stream(
        m_dot=np.array([1.0, 2.0, 3.0]),
        T=np.array([300.0, 310.0, 320.0]),
        p=np.array([1e5, 2e5, 3e5]),
        fluid=gm.WATER,
    )


def _break_middles():
    stubborn = Stubborn().update_params(scale=3.0)
    hooked = Gain().update_params(scale=3.0)
    hooked.register_forward_pre_hook(lambda module, inlets: None)
    return {"stateful": Tank(), "untraceable": stubborn, "pre-hooked": hooked}


@pytest.mark.parametrize("kind", ["stateful", "untraceable", "pre-hooked"])
def test_a_leaf_break_keeps_the_rest_in_the_graph(kind, chain_inlet):
    """The child runs untraced per row; its values flow into formulas, sums and outlets."""
    chain = Chain(_break_middles()[kind])
    drives = np.array([1.0, 2.0, 3.0])
    result = run(chain, {"inlet": chain_inlet}, {"drive": drives})
    expected = _chain_rows(chain, chain_inlet, drives)
    assert result.graph is not None and result.breaks == []
    assert [path for path, _ in result.graph.breaks] == ["middle"]
    assert result.graph.nodes[0].op != "break" and "break(" in result.graph.describe()
    for name in ("value", "pressure", "electricity"):
        assert result.outputs[name].tolist() == [row.outputs[name] for row in expected]
    assert result.outlets["outlet"]["p"].tolist() == [row.outlets.outlet.p for row in expected]


def test_a_failing_break_row_raises_its_own_exception(chain_inlet):
    """The exception of the first failing row of the child is raised as it was."""
    chain = Chain(Stubborn().update_params(scale=3.0))
    with pytest.raises(PhysicsRangeError, match="middle: gain = -2.0"):
        run(chain, {"inlet": chain_inlet}, {"drive": np.array([1.0, -2.0, -3.0])})


def test_a_break_node_runs_on_the_python_backend_too(chain_inlet):
    """With scalar rows the break node returns plain Python values."""
    chain = Chain(Tank())
    expected = run(chain, {"inlet": chain_inlet}, {"drive": 1.0})
    actual = run(chain, {"inlet": chain_inlet}, {"drive": 1.0}, backend="python")
    for name, values in expected.outputs.items():
        assert actual.outputs[name].tolist() == values.tolist()


def test_a_pre_hook_of_a_break_runs_once_per_row(chain_inlet):
    """A pre-hooked child is called on the plain path for every row, hooks included."""
    calls = []
    middle = Gain().update_params(scale=3.0)
    middle.register_forward_pre_hook(lambda module, inlets: calls.append(1))
    run(Chain(middle), {"inlet": chain_inlet}, {"drive": 1.0})
    assert len(calls) == 3


def test_a_composite_child_that_cannot_be_traced_breaks_the_whole_root(chain_inlet):
    """A composite is never a node: its leaves' records feed the parent, so the root breaks."""
    chain = Chain(Opaque())
    result = run(chain, {"inlet": chain_inlet}, {"drive": 1.0})
    assert result.graph is None and "float()" in result.breaks[0]


def test_a_marked_observer_on_a_leaf_child_is_not_a_break_node(chain_inlet):
    """Replaying it per row is only possible at the root, so the root falls back as a whole."""
    middle = Gain().update_params(scale=3.0)
    middle.register_forward_hook(observer(lambda module, inlets, outlets: None))
    result = run(Chain(middle), {"inlet": chain_inlet}, {"drive": 1.0})
    assert result.graph is None and "observer" in result.breaks[0]


def test_a_row_whose_outlet_fluid_differs_from_the_probe_fails(chain_inlet):
    """The static outlet fluid comes from a probe; another fluid on a row is a failed row."""
    chain = Chain(Switcher())
    with pytest.raises(TraceError, match="fluid differs from the traced one"):
        run(chain, {"inlet": chain_inlet}, {"drive": 1.0})
