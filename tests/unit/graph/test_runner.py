"""The runner evaluates arrays in one traced call or falls back to untraced calls."""

import numpy as np
import pytest

import gemini as gm
from gemini.errors import PhysicsRangeError
from gemini.graph import GraphCache, Proxy, run
from gemini.utils.hooks import observer


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
