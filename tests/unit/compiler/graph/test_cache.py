"""The cache retraces only when a guard changes."""

import copy
import gc
import pickle
import weakref

import gemini as gm
from gemini.compiler.graph import GraphCache, graph_cache


def test_numeric_parameter_values_do_not_retrace_but_guards_do(gain):
    """New numeric values reuse the graph; text values, hooks and output mode retrace."""
    cache = GraphCache()
    fluids = {"fluid_in": gain.fluid}
    first = cache.graph(gain, fluids)
    gain.set_params("", {"scale": 7.0})
    assert cache.graph(gain, fluids) is first and cache.traces == 1
    gain.set_params("", {"label": "y"})
    assert cache.graph(gain, fluids) is not first and cache.traces == 2
    handle = gain.register_forward_hook(lambda module, inlets, outlets: None)
    cache.graph(gain, fluids)
    handle.remove()
    with gm.modules.no_outputs():
        cache.graph(gain, fluids)
    assert cache.traces == 4


def test_a_changed_module_fluid_retraces(gain):
    """The module's own fluid is baked into a trace, so changing it makes a new graph."""
    cache = GraphCache()
    fluids = {"fluid_in": gain.fluid}
    first = cache.graph(gain, fluids)
    gain.fluid = gm.WATER
    assert cache.graph(gain, fluids) is not first and cache.traces == 2


def test_graph_breaks_are_remembered(gain):
    """A module that cannot be traced is a cached root break graph, never an error."""
    cache = GraphCache()
    gain.register_forward_pre_hook(lambda module, inlets: None)
    graphs = [cache.graph(gain, {"fluid_in": gain.fluid}) for _ in range(2)]
    assert graphs[0] is graphs[1] and graphs[0].root is gain
    assert "pre-hooks" in graphs[0].breaks[0][1]
    assert cache.traces == 1


def test_structural_parameter_values_are_guards(stepper):
    """A structural value retraces when it changes; a numeric one next to it does not."""
    module = stepper
    cache = GraphCache()
    fluids = {"fluid_in": module.fluid}
    first = cache.graph(module, fluids)
    assert "steps" not in first.inputs and "increment" in first.inputs
    module.set_params("", {"increment": 5.0})
    assert cache.graph(module, fluids) is first and cache.traces == 1
    module.set_params("", {"steps": 3})
    assert cache.graph(module, fluids) is not first and cache.traces == 2


def test_a_change_deep_in_the_tree_retraces(line):
    """Guards cover every module: a text parameter or a fluid below the root retrace."""
    cache = GraphCache()
    fluids = {"fluid_in": line.fluid}
    first = cache.graph(line, fluids)
    line.gain.set_params("", {"scale": 9.0})
    line.second.set_params("", {"scale": 9.0})
    assert cache.graph(line, fluids) is first and cache.traces == 1
    line.gain.set_params("", {"label": "y"})
    assert cache.graph(line, fluids) is not first and cache.traces == 2
    line.first.fluid = gm.WATER
    cache.graph(line, fluids)
    assert cache.traces == 3


def test_a_hook_below_the_root_is_a_guard(line):
    """Adding a writing hook to a child retraces the composite."""
    cache = GraphCache()
    fluids = {"fluid_in": line.fluid}
    cache.graph(line, fluids)
    line.gain.register_forward_hook(lambda module, inlets, outlets: setattr(module, "rise", 1.0))
    cache.graph(line, fluids)
    assert cache.traces == 2


def test_stepped_is_a_guard(tank):
    """A stepped graph of a stateful module is a different graph from the unstepped one."""
    cache = GraphCache()
    fluids = {"fluid_in": tank.fluid}
    unstepped = cache.graph(tank, fluids)
    stepped = cache.graph(tank, fluids, stepped=True)
    assert stepped is not unstepped and stepped.stepped and not unstepped.stepped
    assert cache.graph(tank, fluids, stepped=True) is stepped and cache.traces == 2


def test_a_module_holds_one_cache_that_an_engine_uses(gain):
    """The graphs outlive an engine: a new engine on the module finds them."""
    assert graph_cache(gain) is graph_cache(gain)
    assert gm.Engine(gain)._graph_cache is graph_cache(gain)
    assert graph_cache(gm.modules.ESP()) is not graph_cache(gain)


def test_a_copied_module_starts_with_an_empty_cache(gain):
    """A graph belongs to the module object it traced, so a copy traces its own."""
    cache = graph_cache(gain)
    cache.graph(gain, {"fluid_in": gain.fluid})
    for copied in (copy.deepcopy(gain), pickle.loads(pickle.dumps(gain))):
        assert copied._graph_cache is not cache
        assert copied._graph_cache.traces == 0
        assert copied._graph_cache.graph(copied, {"fluid_in": copied.fluid}).root is not gain


def test_a_cache_does_not_keep_a_finished_module_alive(gain):
    """A module and its graphs are freed together, although a graph may refer to its module."""
    module = copy.deepcopy(gain)
    graph_cache(module).graph(module, {"fluid_in": module.fluid})
    reference = weakref.ref(module)
    del module
    gc.collect()
    assert reference() is None
