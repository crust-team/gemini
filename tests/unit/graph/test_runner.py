"""The runner evaluates arrays in one traced call or falls back to untraced calls."""

import numpy as np
import pytest

import gemini as gm
from gemini.errors import PhysicsRangeError
from gemini.graph import Proxy, run


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
