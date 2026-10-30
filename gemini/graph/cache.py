"""``GraphCache``: one traced graph per module, retraced only when a guard changes.

The guards are what the trace bakes in: the module class and its declaration names, the
values of non-numeric and structural parameters and the shapes of numeric ones, the registered
hooks, whether outputs are enabled, the runtime precision, the module's own fluid and the inlet
fluids. Numeric parameter values, constants and inputs are graph inputs, so changing them never
retraces. A module that cannot be traced is remembered with its ``TraceError`` until a guard
changes. Every graph is traced once and then merged by ``eliminate_common_subexpressions``;
``GraphCache(optimize=False)`` keeps the traced graph as it is, for benchmarks and debugging.
"""

import weakref

from gemini.core import runtime
from gemini.core.modules.module import outputs_enabled
from gemini.errors import TraceError
from gemini.graph.passes import eliminate_common_subexpressions
from gemini.graph.tracer import Tracer, traced_shape


class GraphCache:
    """Traced graphs (or graph breaks) by module, with the guards they were traced under."""

    def __init__(self, optimize=True):
        """Start empty; ``traces`` counts the traces made and ``optimize`` runs the graph passes."""
        self.optimize = optimize
        self._entries = weakref.WeakKeyDictionary()
        self.traces = 0

    def graph(self, module, fluids):
        """Return the graph of ``module`` for inlet ``fluids``; raise ``TraceError`` for a break."""
        guards = _guards(module, fluids)
        entry = self._entries.get(module)
        if entry is None or entry[0] != guards:
            entry = (guards, self._trace(module, fluids))
            self._entries[module] = entry
        if isinstance(entry[1], TraceError):
            raise entry[1]
        return entry[1]

    def _trace(self, module, fluids):
        self.traces += 1
        try:
            graph = Tracer().trace(module, fluids)
        except TraceError as error:
            return error
        if self.optimize:
            eliminate_common_subexpressions(graph)
        return graph


def _guards(module, fluids):
    parameters = tuple(
        (name, _parameter_guard(declaration)) for name, declaration in module._parameters.items()
    )
    return (
        type(module),
        tuple(module._declarations()),
        parameters,
        tuple(module._hooks.values()),
        tuple(module._pre_hooks.values()),
        outputs_enabled(),
        runtime.get_precision(),
        tuple(fluids[name] for name in module._inlets),
    )


def _parameter_guard(declaration):
    shape = traced_shape(declaration)
    if shape is None:
        return ("value", repr(declaration.value))
    return ("traced", shape)
