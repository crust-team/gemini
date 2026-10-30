"""The cache retraces only when a guard changes."""

import pytest

import gemini as gm
from gemini.errors import TraceError
from gemini.graph import GraphCache


def test_numeric_parameter_values_do_not_retrace_but_guards_do(gain):
    """New numeric values reuse the graph; text values, hooks and output mode retrace."""
    cache = GraphCache()
    fluids = {"inlet": gain.fluid}
    first = cache.graph(gain, fluids)
    gain.update_params(scale=7.0)
    assert cache.graph(gain, fluids) is first and cache.traces == 1
    gain.update_params(label="y")
    assert cache.graph(gain, fluids) is not first and cache.traces == 2
    handle = gain.register_forward_hook(lambda module, inlets, outlets: None)
    cache.graph(gain, fluids)
    handle.remove()
    with gm.no_outputs():
        cache.graph(gain, fluids)
    assert cache.traces == 4


def test_a_changed_module_fluid_retraces(gain):
    """The module's own fluid is baked into a trace, so changing it makes a new graph."""
    cache = GraphCache()
    fluids = {"inlet": gain.fluid}
    first = cache.graph(gain, fluids)
    gain.fluid = gm.WATER
    assert cache.graph(gain, fluids) is not first and cache.traces == 2


def test_graph_breaks_are_remembered(gain):
    """A module that cannot be traced raises its cached ``TraceError`` without retracing."""
    cache = GraphCache()
    gain.register_forward_pre_hook(lambda module, inlets: None)
    for _ in range(2):
        with pytest.raises(TraceError, match="pre-hooks"):
            cache.graph(gain, {"inlet": gain.fluid})
    assert cache.traces == 1


def test_structural_parameter_values_are_guards(stepper):
    """A structural value retraces when it changes; a numeric one next to it does not."""
    module = stepper
    cache = GraphCache()
    fluids = {"inlet": module.fluid}
    first = cache.graph(module, fluids)
    assert "steps" not in first.inputs and "increment" in first.inputs
    module.update_params(increment=5.0)
    assert cache.graph(module, fluids) is first and cache.traces == 1
    module.update_params(steps=3)
    assert cache.graph(module, fluids) is not first and cache.traces == 2
