"""``Tracer``: run one module call on traced values and record it as a ``Graph``.

The trace follows the fixed order of ``Module._evaluate``: ``forward``, then (unless
``no_outputs()`` is active) ``_compute_outputs``, formula outputs, forward hooks and
``_check_outputs``, which runs once here. Inlet stream fields (a ``Stream`` of traced values
whose ``Fluid`` is the concrete, static one), controls, boundaries, numeric parameters and the
constants the physics uses become named graph inputs; non-numeric parameter values are trace
guards (see ``cache``). A forward hook that writes an
output is part of the graph; one that only reads is an observer, replayed per row after a run.
Anything the trace cannot follow raises ``TraceError``, which makes the module a graph break.
"""

import numbers

from gemini.core import runtime
from gemini.core.modules.module import _Call, _current_call, outputs_enabled
from gemini.core.types.flows import Stream
from gemini.core.types.ports import Ports
from gemini.errors import TraceError
from gemini.graph.graph import Graph

STREAM_FIELDS = (("m_dot", "kg/s"), ("T", "K"), ("p", "Pa"))
"""Stream fields of every inlet and outlet in the graph, with their units."""


class Tracer:
    """Trace one leaf module at a time; the engine will link module graphs."""

    def trace(self, module, fluids):
        """Return the graph of one call of ``module``; ``fluids`` maps inlet names to fluids."""
        _check_traceable(module)
        graph = Graph(module.path)
        inlets = Ports(
            {name: _inlet(graph, name, fluids[name]) for name in module._inlets},
            path=module.path,
        )
        call = _Call(
            module=module,
            inputs=_inputs(graph, module),
            outputs={} if outputs_enabled() else None,
            parent=None,
            parameters=_parameters(graph, module),
        )
        token = _current_call.set(call)
        try:
            outlets = Ports(_forward(module, inlets), path=module.path)
            if call.outputs is not None:
                _trace_outputs(graph, module, call, inlets, outlets)
        finally:
            _current_call.reset(token)
        for port, stream in outlets.items():
            graph.outlet_fluids[port] = stream.fluid
            for field, _ in STREAM_FIELDS:
                graph.output(f"outlets.{port}.{field}", getattr(stream, field))
        for name, value in (call.outputs or {}).items():
            graph.output(f"outputs.{name}", value)
        return graph


def _check_traceable(module):
    """Refuse what the prototype does not trace; each refusal is a graph break."""
    reasons = []
    if not module.is_leaf:
        reasons.append("a composite (the engine links leaf graphs)")
    if module.stateful:
        reasons.append("stateful (needs scan)")
    if module._pre_hooks:
        reasons.append("has forward pre-hooks")
    if runtime.get_precision() != "float64":
        reasons.append("runtime precision is not float64")
    if reasons:
        raise TraceError(f"{module.path}: cannot be traced: {'; '.join(reasons)}")


def _inlet(graph, name, fluid):
    """Return the traced stream of one inlet: graph inputs for its fields, the fixed fluid."""
    fields = {field: graph.input(f"{name}.{field}", "inlet", unit) for field, unit in STREAM_FIELDS}
    return Stream._trusted(fluid=fluid, **fields)


def _inputs(graph, module):
    """Return traced controls and boundaries by name."""
    inputs = {}
    for role, declarations in (("control", module._controls), ("boundary", module._boundaries)):
        for name, declaration in declarations.items():
            inputs[name] = graph.input(name, role, declaration.unit)
    return inputs


def _parameters(graph, module):
    """Return traced numeric parameters by name; other values stay as they are (guards)."""
    parameters = {}
    for name, declaration in module._parameters.items():
        value = declaration.value
        shape = parameter_shape(value)
        if shape is None:
            parameters[name] = value
            continue
        parameters[name] = graph.input(name, "parameter", declaration.unit, shape)
    return parameters


def parameter_shape(value):
    """Return ``()`` for a numeric value, ``(n,)`` for a numeric vector, else ``None``."""
    if _is_number(value):
        return ()
    if isinstance(value, (list, tuple)) and value and all(_is_number(item) for item in value):
        return (len(value),)
    return None


def _is_number(value):
    return isinstance(value, numbers.Real) and not isinstance(value, bool)


def _forward(module, inlets):
    """Run ``forward`` and check its outlet names; values are traced, so not validated."""
    returned = module.forward(inlets)
    module._check_outlet_names(returned)
    return {name: returned[name] for name in module._outlets}


def _trace_outputs(graph, module, call, inlets, outlets):
    """Trace the output step and classify each forward hook as part of the graph or observer."""
    module._compute_outputs(inlets, outlets)
    module._compute_formula_outputs(call)
    for hook in tuple(module._hooks.values()):
        before = dict(call.outputs)
        try:
            hook(module, inlets, outlets)
        except TraceError as error:
            raise TraceError(f"{module.path}: forward hook {hook!r}: {error}") from error
        written = [name for name, value in call.outputs.items() if before.get(name) is not value]
        if not written:
            graph.observers.append(hook)
    module._check_outputs(call.outputs)
