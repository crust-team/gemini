"""The graph checks the declared bounds of controls, boundaries, outputs and inlets."""

import numpy as np
import pytest

import gemini as gm
from gemini.errors import DeclarationError, PhysicsRangeError
from gemini.graph import Tracer, run
from tests.fixtures.graph_run import graph_outputs


def _inlet(pressures):
    count = len(pressures)
    return gm.Stream(
        m_dot=np.ones(count),
        T=np.full(count, 300.0),
        p=np.array(pressures),
        fluid=gm.WATER,
    )


def _run(module, pressures, setpoint, ambient=300.0):
    inputs = {"setpoint": np.array(setpoint), "ambient": ambient}
    return run(module, {"inlet": _inlet(pressures)}, inputs)


def test_within_bounds_the_values_equal_the_untraced_call(bounded):
    """The checks do not change a valid row; a ``None`` ratio is NaN."""
    result = _run(bounded, [2e5, 3e5], [1e5, 2e5], ambient=np.array([300.0, 2000.0]))
    assert result.outputs["margin"].tolist() == [1e5, 1e5]
    assert result.outputs["profile"].tolist() == [[1e5, 1e5 - 1], [2e5, 2e5 - 1]]
    assert result.outputs["share"][0] == 0.5 and np.isnan(result.outputs["share"][1])


@pytest.mark.parametrize(
    ("pressures", "setpoint", "ambient"),
    [
        ([2e5, 3e5], [1e5, -5.0], 300.0),
        ([2e5, 3e5], [1e5, 2e5], np.array([300.0, -3.0])),
        ([2e5, 3e5], [1e5, 5e5], 300.0),
    ],
    ids=["control", "boundary", "output"],
)
def test_a_violated_bound_raises_a_declaration_error(bounded, pressures, setpoint, ambient):
    """A negative control or boundary and a negative output raise like ``Declaration.validate``."""
    with pytest.raises(DeclarationError, match="bounded"):
        _run(bounded, pressures, setpoint, ambient)
    with pytest.raises(DeclarationError):
        for row in range(2):
            bounded(
                inlet=gm.Stream(m_dot=1.0, T=300.0, p=pressures[row], fluid=gm.WATER),
                setpoint=setpoint[row],
                ambient=ambient[row] if isinstance(ambient, np.ndarray) else ambient,
            )


def test_a_list_item_out_of_bounds_fails_the_row(bounded):
    """Each item of a list output is checked: the second item is the setpoint minus one."""
    with pytest.raises(DeclarationError, match="profile"):
        _run(bounded, [2e5], [0.5])


def test_the_bound_fails_even_when_the_value_does_not_reach_an_output(bounded):
    """Bound checks guard every output, so a control the arithmetic ignores still fails."""
    graph = Tracer().trace(bounded, {"inlet": bounded.fluid})
    bounded_checks = [
        check for check in graph.checks if check.attributes["error"] is DeclarationError
    ]
    assert bounded_checks
    for node in graph.outputs.values():
        assert all(check in node.guards for check in bounded_checks)


def test_inlet_limits_fail_the_row_with_the_stream_error(gain):
    """The traced inlet carries the stream limits, since the engine feeds raw columns."""
    graph = Tracer().trace(gain, {"inlet": gain.fluid})
    feeds = {
        "inlet.m_dot": np.ones(2),
        "inlet.T": np.array([300.0, 0.0]),
        "inlet.p": np.full(2, 1e5),
        "gain": 1.0,
        "scale": 3.0,
        "REFERENCE": 2.0,
    }
    with pytest.raises(PhysicsRangeError, match="Stream: T = 0.0 K"):
        graph_outputs(graph, feeds)


def test_not_a_number_against_a_bound_fails_like_the_untraced_call(bounded):
    """Not-a-number satisfies no bound, so it fails the row like an untraced call."""
    with pytest.raises(DeclarationError, match="bounded"):
        _run(bounded, [2e5], [np.nan])
    with pytest.raises(DeclarationError):
        bounded(inlet=gm.Stream(m_dot=1.0, T=300.0, p=2e5, fluid=gm.WATER), setpoint=np.nan)
