"""The tracer records a whole module call with named inputs by role."""

import pytest

import gemini as gm
from gemini.core.modules.plants import Doublet
from gemini.errors import OutputError, TraceError
from gemini.graph import Tracer
from gemini.graph.tracer import parameter_shape


def test_trace_names_inputs_by_role_and_records_outputs(gain):
    """Inlet fields, fluid properties, controls, parameters and constants are inputs."""
    graph = Tracer().trace(gain, {"inlet": gain.fluid})
    roles = {name: node.role for name, node in graph.inputs.items()}
    assert roles == {
        "inlet.m_dot": "inlet",
        "inlet.T": "inlet",
        "inlet.p": "inlet",
        "inlet.rho_l": "inlet",
        "inlet.rho_g": "inlet",
        "inlet.gmf": "inlet",
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


def test_untraceable_modules_name_every_reason(gain):
    """Composites, pre-hooks and float32 precision are graph breaks."""
    with pytest.raises(TraceError, match="composite"):
        Tracer().trace(Doublet(), {"return_in": gain.fluid})
    gain.register_forward_pre_hook(lambda module, inlets: None)
    with gm.runtime.settings(precision="float32"):
        with pytest.raises(TraceError, match="pre-hooks; runtime precision"):
            Tracer().trace(gain, {"inlet": gain.fluid})


def test_parameter_shapes():
    """Numbers are scalars, numeric sequences vectors and anything else a guard."""
    assert parameter_shape(2) == () and parameter_shape([1.0, 2.0]) == (2,)
    assert parameter_shape(True) is None and parameter_shape("x") is None
    assert parameter_shape(None) is None and parameter_shape([]) is None
