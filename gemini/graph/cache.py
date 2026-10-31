"""``GraphCache``: one traced graph per module, retraced only when a guard changes.

The guards are what the trace bakes in, for every module of the tree (a change anywhere below
the root retraces): the module class and its declaration names, the values of non-numeric and
structural parameters and the shapes of numeric ones, the registered hooks and the module's own
fluid; and, once, whether outputs are enabled, the runtime precision, the inlet fluids and
whether the graph is ``stepped``. Numeric parameter values, constants and inputs are graph
inputs, so changing them never retraces. The cache stores graphs only: a module that cannot be
traced is a root break graph (see ``rootbreak``), remembered until a guard changes. Every
graph is traced once and then merged by
``eliminate_common_subexpressions``; ``GraphCache(optimize=False)`` keeps the traced graph as it
is, for benchmarks and debugging.

``graph_cache`` gives the one cache of a module, which the module holds: a graph keeps a strong
reference to its module (a root break, a break node), so a cache outside the module would keep
the module alive, and a module is not shared across threads, so neither is its cache.
"""

import weakref

from gemini.backends import runtime
from gemini.graph.passes import eliminate_common_subexpressions
from gemini.graph.tracer import Tracer, traced_shape
from gemini.modules.module import outputs_enabled


class GraphCache:
    """Traced graphs (or graph breaks) by module, with the guards they were traced under."""

    def __init__(self, optimize=True):
        """Start empty; ``traces`` counts the traces made and ``optimize`` runs the graph passes."""
        self.optimize = optimize
        self._entries = weakref.WeakKeyDictionary()
        self.traces = 0

    def __reduce__(self):
        """Copy or pickle as an empty cache: a graph belongs to the module object it traced."""
        return GraphCache, (self.optimize,)

    def graph(self, module, fluids, stepped=False):
        """Return the graph of ``module`` for inlet ``fluids``; a break is a root break graph."""
        guards = _guards(module, fluids, stepped)
        entry = self._entries.get(module)
        if entry is None or entry[0] != guards:
            entry = (guards, self._trace(module, fluids, stepped))
            self._entries[module] = entry
        return entry[1]

    def _trace(self, module, fluids, stepped):
        self.traces += 1
        graph = Tracer().trace(module, fluids, stepped)
        if self.optimize:
            eliminate_common_subexpressions(graph)
        return graph


def graph_cache(module):
    """Return the one ``GraphCache`` of ``module``, so its graphs outlive any one engine."""
    if module._graph_cache is None:
        module._graph_cache = GraphCache()
    return module._graph_cache


def _guards(module, fluids, stepped):
    tree = tuple((path, _module_guards(member)) for path, member in module.named_modules())
    return (
        tree,
        outputs_enabled(),
        runtime.get_precision(),
        tuple(fluids[name] for name in module._fed_inlets()),
        stepped,
    )


def _module_guards(module):
    parameters = tuple(
        (name, _parameter_guard(declaration)) for name, declaration in module._parameters.items()
    )
    return (
        type(module),
        tuple(module._declarations()),
        parameters,
        tuple(module._hooks.values()),
        tuple(module._pre_hooks.values()),
        module.fluid,
    )


def _parameter_guard(declaration):
    shape = traced_shape(declaration)
    if shape is None:
        return ("value", repr(declaration.value))
    return ("traced", shape)
