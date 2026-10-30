"""The tracer records a whole module call with named inputs by role."""

import numpy as np
import pytest

import gemini as gm
from gemini.core.types.declarations import UNSET
from gemini.errors import MissingValueError, OutputError, PhysicsRangeError, TraceError
from gemini.graph import Tracer, run
from gemini.graph.tracer import parameter_shape
from gemini.utils.hooks import observer


def test_trace_names_inputs_by_role_and_records_outputs(gain):
    """Inlet fields (the fluid is static), controls, parameters and constants are inputs."""
    graph = Tracer().trace(gain, {"inlet": gain.fluid})
    roles = {name: node.role for name, node in graph.inputs.items()}
    assert roles == {
        "inlet.m_dot": "inlet",
        "inlet.T": "inlet",
        "inlet.p": "inlet",
        "gain": "control",
        "scale": "parameter",
        "REFERENCE": "constant",
    }
    assert set(graph.outputs) == {
        "outlets.outlet.m_dot",
        "outlets.outlet.T",
        "outlets.outlet.p",
        "outputs.rise",
        "outputs.boost",
    }
    assert graph.inputs["inlet.p"].unit == "Pa" and graph.outlet_fluids == {"outlet": gain.fluid}
    assert all(node.op != "input" or node.name for node in graph.nodes)
    assert 3.0 not in [operand for node in graph.nodes for operand in node.operands]


def test_no_outputs_traces_only_the_fluid_step(gain):
    """Under ``no_outputs()`` the graph has outlet fields only."""
    with gm.no_outputs():
        graph = Tracer().trace(gain, {"inlet": gain.fluid})
    assert all(name.startswith("outlets.") for name in graph.outputs)


def test_hooks_are_classified_by_what_they_do(gain):
    """A writing hook joins the graph, a reading one is an observer, a failing one breaks."""

    def doubles(module, inlets, outlets):
        module.boost = module.boost * 2

    def reads(module, inlets, outlets):
        return module.rise

    gain.register_forward_hook(doubles)
    gain.register_forward_hook(reads)
    graph = Tracer().trace(gain, {"inlet": gain.fluid})
    assert graph.observers == [reads]
    assert graph.outputs["outputs.boost"].op == "mul"
    gain.register_forward_hook(lambda module, inlets, outlets: float(module.rise))
    with pytest.raises(TraceError, match="forward hook .*float"):
        Tracer().trace(gain, {"inlet": gain.fluid})


def test_unassigned_outputs_fail_at_trace_time(gain):
    """``_check_outputs`` runs once during the trace."""

    class Forgetful(type(gain)):
        def _compute_outputs(self, inlets, outlets):
            self.rise = 0.0

    module = Forgetful().update_params(scale=1.0)
    with pytest.raises(OutputError, match="boost"):
        Tracer().trace(module, {"inlet": module.fluid})


def test_untraceable_modules_name_every_reason(gain, tank):
    """Stateful modules, pre-hooks and float32 precision are graph breaks."""
    with pytest.raises(TraceError, match="stateful"):
        Tracer().trace(tank, {"inlet": gain.fluid})
    gain.register_forward_pre_hook(lambda module, inlets: None)
    with gm.runtime.settings(precision="float32"):
        with pytest.raises(TraceError, match="pre-hooks; runtime precision"):
            Tracer().trace(gain, {"inlet": gain.fluid})


def test_parameter_shapes():
    """Numbers are scalars, numeric sequences vectors and anything else a guard."""
    assert parameter_shape(2) == () and parameter_shape([1.0, 2.0]) == (2,)
    assert parameter_shape(True) is None and parameter_shape("x") is None
    assert parameter_shape(None) is None and parameter_shape([]) is None


def test_a_stream_built_in_forward_traces_and_keeps_its_limits(gain):
    """Building a ``Stream`` from traced values records its limit checks as ``ops.check``."""

    class Drop(type(gain)):
        def forward(self, inlets):
            inlet = inlets.inlet
            drop = self.gain * 1e6
            return {
                "outlet": gm.Stream(
                    m_dot=inlet.m_dot, T=inlet.T, p=inlet.p - drop, fluid=inlet.fluid
                )
            }

    module = Drop().update_params(scale=1.0)
    graph = Tracer().trace(module, {"inlet": module.fluid})
    assert any(node.op == "check" for node in graph.nodes)
    stream = gm.Stream(m_dot=np.array([1.0, 1.0]), T=300.0, p=np.array([2e5, 1e5]))
    assert run(module, {"inlet": stream}, {"gain": 0.0}).outlets["outlet"]["p"].tolist() == [
        2e5,
        1e5,
    ]
    with pytest.raises(PhysicsRangeError, match="p = -800000.0 Pa"):
        run(module, {"inlet": stream}, {"gain": 1.0})


def test_composite_inputs_are_named_by_relative_path(line):
    """Child controls, boundaries and parameters are prefixed; the root's are not."""
    graph = Tracer().trace(line, {"inlet": line.fluid})
    roles = {name: node.role for name, node in graph.inputs.items()}
    assert roles == {
        "inlet.m_dot": "inlet",
        "inlet.T": "inlet",
        "inlet.p": "inlet",
        "boost": "control",
        "first.scale": "parameter",
        "gain.scale": "parameter",
        "REFERENCE": "constant",
        "second.draw": "control",
        "second.scale": "parameter",
    }
    assert list(graph.outputs)[3:] == [
        "outputs.rise",
        "outputs.pressure",
        "outputs.electricity",
        "outputs.efficiency",
    ]


def test_a_child_called_twice_reuses_its_inputs(twice):
    """The second call finds the first call's graph inputs."""
    graph = Tracer().trace(twice, {"inlet": twice.fluid})
    assert [name for name in graph.inputs if name.startswith("gain")] == ["gain.gain", "gain.scale"]


def test_composite_without_outputs_traces_the_fluid_step(line):
    """Under ``no_outputs()`` a composite graph has outlet fields only."""
    with gm.no_outputs():
        graph = Tracer().trace(line, {"inlet": line.fluid})
    assert all(name.startswith("outlets.") for name in graph.outputs)


def test_uninitialized_parameters_of_the_tree_are_refused(line):
    """A parameter without a value anywhere below the root cannot be traced."""
    line.gain._parameters["scale"].value = UNSET
    with pytest.raises(MissingValueError, match="line: uninitialized parameters"):
        Tracer().trace(line, {"inlet": line.fluid})


def test_marked_observers_on_a_child_are_a_graph_break(line):
    """An observer is replayed per row for the root only, so one on a child breaks the root."""
    line.gain.register_forward_hook(observer(lambda module, inlets, outlets: None))
    with pytest.raises(TraceError, match="gain: observer hooks on a child"):
        Tracer().trace(line, {"inlet": line.fluid})


def test_a_reading_hook_on_a_leaf_child_makes_it_a_break_node(line):
    """An unmarked hook that only reads cannot be replayed, so the leaf child runs untraced."""
    line.gain.register_forward_hook(lambda module, inlets, outlets: module.rise)
    graph = Tracer().trace(line, {"inlet": line.fluid})
    assert [path for path, _ in graph.breaks] == ["gain"]
    assert "only reads" in graph.breaks[0][1]


def test_writing_hooks_on_a_child_join_the_graph(line):
    """A hook that writes an output of a child is part of the graph."""

    def doubles(module, inlets, outlets):
        module.rise = module.rise * 2

    line.gain.register_forward_hook(doubles)
    inlet = gm.Stream(m_dot=np.ones(3), T=np.full(3, 300.0), p=np.full(3, 1e5), fluid=line.fluid)
    result = run(line, {"inlet": inlet}, {"boost": np.array([1.0, 2.0, 3.0])})
    assert result.graph is not None
    assert result.outputs["rise"].tolist() == [12.0, 24.0, 36.0]
