"""The traced ESP on NumPy equals the untraced tick-by-tick ESP on the short window.

``RTOL`` is the documented equivalence tolerance of the NumPy backend against the Python path.
"""

import copy
import inspect

import numpy as np
import pytest

import gemini as gm
from gemini.core.modules.pumps import esp as esp_file
from gemini.core.types.flows import Stream
from gemini.errors import PhysicsRangeError
from gemini.graph import GraphCache, Proxy, run

RTOL = 1e-12
COLUMNS = ["suction.m_dot", "suction.T", "suction.p", "frequency"]


@pytest.fixture(scope="module")
def week(fast_frame):
    """Return the first seven days of ESP inputs in SI: mass flow, T, p and frequency."""
    frame = fast_frame.iloc[: 7 * 96][[f"doublet.esp.{column}" for column in COLUMNS]].dropna()
    return frame.to_numpy()


@pytest.fixture
def esp(shared_plant):
    """Return an isolated copy of the shared plant's ESP."""
    return copy.deepcopy(shared_plant.doublet.esp)


def _suction(esp, week):
    density = esp.fluid.properties(None, None).density
    return Stream(m_dot=week[:, 0] * density, T=week[:, 1], p=week[:, 2], fluid=esp.fluid)


def _untraced(esp, week):
    suction = _suction(esp, week)
    return [
        esp(
            suction=gm.Stream(
                m_dot=suction.m_dot[row], T=week[row, 1], p=week[row, 2], fluid=esp.fluid
            ),
            frequency=week[row, 3],
        )
        for row in range(len(week))
    ]


def _assert_equal(traced, expected):
    """Compare every output and the discharge fields within ``RTOL``."""
    for name in expected[0].outputs:
        values = [row.outputs[name] for row in expected]
        np.testing.assert_allclose(traced.outputs[name], values, rtol=RTOL, atol=0, err_msg=name)
    for field in ("m_dot", "T", "p"):
        values = [getattr(row.outlets.discharge, field) for row in expected]
        np.testing.assert_allclose(traced.outlets["discharge"][field], values, rtol=RTOL, atol=0)


def test_numpy_backend_equals_the_untraced_path(esp, week):
    """Every ESP output and outlet field of one traced NumPy call matches tick by tick."""
    traced = run(esp, {"suction": _suction(esp, week)}, {"frequency": week[:, 3]})
    expected = _untraced(esp, week)
    assert traced.breaks == []
    assert set(traced.outputs) == set(esp.outputs(recurse=False)) == set(expected[0].outputs)
    _assert_equal(traced, expected)


def test_python_backend_interprets_the_same_graph(esp, week):
    """The graph on the Python backend, row by row, gives the untraced values."""
    traced = run(esp, {"suction": _suction(esp, week[:4])}, {"frequency": week[:4, 3]})
    expected = _untraced(esp, week[:4])
    for row in range(4):
        one = week[row : row + 1]
        scalar = run(
            esp, {"suction": _suction(esp, one)}, {"frequency": one[0, 3]}, backend="python"
        )
        assert scalar.outputs["head"][0] == pytest.approx(expected[row].outputs.head, rel=RTOL)
        assert traced.outputs["power"][row] == expected[row].outputs.power


def test_parameters_and_constants_are_named_inputs_without_baked_values(esp):
    """The graph reads parameters and constants as inputs; no parameter value is a literal."""
    graph = GraphCache().graph(esp, {"suction": esp.fluid})
    parameters = set(graph.by_role("parameter"))
    assert {"no_stages", "head_coeff", "power_coeff", "motor_efficiency", "bep_flow"} <= parameters
    assert set(graph.by_role("constant")) == {
        "ESP_REFERENCE_FREQUENCY",
        "ESP_EFFICIENCY_FLOW_FACTOR",
        "ESP_MIN_EFFICIENCY_POWER",
    }
    assert graph.inputs["head_coeff"].shape == (6,) and graph.inputs["frequency"].unit == "Hz"
    literals = {
        operand for node in graph.nodes for operand in node.operands if not hasattr(operand, "op")
    }
    baked = {float(esp.no_stages), *esp.head_coeff, esp.bep_flow, 60.0, 135773.0, 0.1}
    assert not literals & (baked - {0.0, 1.0})


def test_retrace_happens_only_when_a_guard_changes(esp, week):
    """New parameter values reuse the graph and change the results; a new hook retraces."""
    cache = GraphCache()
    inlets, inputs = {"suction": _suction(esp, week)}, {"frequency": week[:, 3]}
    before = run(esp, inlets, inputs, cache=cache).outputs["head"]
    esp.update_params(no_stages=2 * esp.no_stages)
    after = run(esp, inlets, inputs, cache=cache).outputs["head"]
    assert cache.traces == 1
    np.testing.assert_allclose(after, 2 * before, rtol=RTOL)
    esp.register_forward_hook(lambda module, inlets, outlets: None)
    run(esp, inlets, inputs, cache=cache)
    assert cache.traces == 2


def test_no_outputs_traces_the_fluid_step_only(esp, week):
    """Under ``no_outputs()`` the traced run returns outlets and no outputs."""
    with gm.no_outputs():
        traced = run(esp, {"suction": _suction(esp, week)}, {"frequency": week[:, 3]})
    assert traced.outputs == {} and traced.breaks == []
    expected = _untraced(esp, week)
    pressures = [row.outlets.discharge.p for row in expected]
    np.testing.assert_allclose(traced.outlets["discharge"]["p"], pressures, rtol=RTOL)


def test_reverse_flow_raises_the_untraced_error_at_the_physics_line(esp, week):
    """A negative flow row raises ``PhysicsRangeError`` with the untraced message and line."""
    suction = _suction(esp, week[:3])
    reversed_flow = suction.with_(m_dot=suction.m_dot * np.array([1, -1, -1]))
    with pytest.raises(PhysicsRangeError) as untraced:
        esp(
            suction=gm.Stream(
                m_dot=reversed_flow.m_dot[1], T=week[1, 1], p=week[1, 2], fluid=esp.fluid
            ),
            frequency=week[1, 3],
        )
    with pytest.raises(PhysicsRangeError) as traced:
        run(esp, {"suction": reversed_flow}, {"frequency": week[:3, 3]})
    assert str(traced.value) == str(untraced.value)
    source, first = inspect.getsourcelines(esp_file.ESP.forward)
    note = traced.value.__notes__[0]
    assert f"{esp_file.__file__}:" in note
    assert first <= int(note.rsplit(":", 1)[1]) < first + len(source)


def test_hooks_on_the_traced_esp(esp, week):
    """A reading hook is replayed, a gm-op hook joins the graph, an untraceable one breaks."""
    inlets, inputs = {"suction": _suction(esp, week)}, {"frequency": week[:, 3]}
    seen = []
    reader = esp.register_forward_hook(lambda module, inlets, outlets: seen.append(module.head))
    traced = run(esp, inlets, inputs)
    reader.remove()
    expected_heads = [row.outputs.head for row in _untraced(esp, week)]
    assert traced.graph.observers and isinstance(seen[0], Proxy)
    assert seen[1:] == pytest.approx(expected_heads, rel=RTOL)

    def motor_loss(module, inlets, outlets):
        module.electricity = module.power / 0.9

    writer = esp.register_forward_hook(motor_loss)
    traced = run(esp, inlets, inputs)
    assert traced.graph.outputs["outputs.electricity"].op == "truediv"
    _assert_equal(traced, _untraced(esp, week))
    writer.remove()

    def untraceable(module, inlets, outlets):
        module.electricity = float(module.power) / 0.9

    esp.register_forward_hook(untraceable)
    broken = run(esp, inlets, inputs)
    assert broken.graph is None and "forward hook" in broken.breaks[0]
    _assert_equal(broken, _untraced(esp, week))
