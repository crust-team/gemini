"""``Tracer``: run one module call on traced values and record it as a ``Graph``.

The module is a leaf or a composite: child calls are recorded by ``Trace`` into the same graph
(see there). The trace follows the fixed order of ``Module._evaluate``: ``forward``, then (unless
``no_outputs()`` is active) ``_compute_outputs``, formula outputs, forward hooks and
``_check_outputs``, which runs once here. Inlet stream fields (a ``Stream`` of traced values
whose ``Fluid`` is the concrete, static one), controls, boundaries, numeric parameters and the
constants the physics uses become named graph inputs; non-numeric and structural parameter
values are trace guards (see ``cache``). A forward hook that writes an
output is part of the graph; one that only reads is an observer, replayed per row after a run.
A hook marked with ``gemini.utils.hooks.observer`` is never called on traced values: it is an
observer by declaration, and so are marked pre-hooks. Any other pre-hook is a graph break.
Anything the trace cannot follow raises ``TraceError``, which makes the module a graph break.
"""

import numbers

from gemini.core import runtime
from gemini.core.modules.module import _Call, _current_call, outputs_enabled
from gemini.core.types.flows import Stream
from gemini.core.types.ports import Ports
from gemini.core.types.results import ModuleResult, Values
from gemini.errors import MissingValueError, TraceError
from gemini.graph.breaks import record_break
from gemini.graph.graph import Graph
from gemini.graph.limits import certain, check_declared_limits
from gemini.graph.node import STREAM_FIELDS
from gemini.utils.hooks import is_observer
from gemini.utils.strings import join_path


class Tracer:
    """Trace one call of a root module, a leaf or a composite with all its child calls."""

    def trace(self, module, fluids):
        """Return the graph of one call of ``module``; ``fluids`` maps inlet names to fluids."""
        _check_traceable(module)
        missing = module.missing_parameters()
        if missing:
            raise MissingValueError(
                f"{module.path}: uninitialized parameters: {', '.join(missing)}"
            )
        module._resolve_formula_outputs()
        graph = Graph(module.path)
        trace = Trace(graph, module)
        inlets = Ports(
            {name: _inlet(graph, name, fluids[name]) for name in module._inlets},
            path=module.path,
        )
        graph.pre_observers.extend(module._pre_hooks.values())
        trace.limit_checks.extend(graph.checks)
        outlets, call = trace.run(module, inlets, {}, None)
        for port, stream in outlets.items():
            graph.outlet_fluids[port] = stream.fluid
            for field, _ in STREAM_FIELDS:
                graph.output(f"outlets.{port}.{field}", getattr(stream, field))
        for name, value in (call.outputs or {}).items():
            graph.output(f"outputs.{name}", value)
        certain(graph, trace.limit_checks)
        return graph


class Trace:
    """The running trace of one root call; module code reaches it as ``call.trace``.

    A call made while the trace runs goes through ``child`` instead of being evaluated: the
    child's controls, boundaries and numeric parameters become graph inputs named
    ``<path relative to the root>.<name>`` (the root's own have no prefix, so a leaf keeps its
    plain names, and a child called twice reuses its inputs), its ``forward``, output step and
    forward hooks are recorded in the same fixed order as a call, and its ``ModuleResult`` holds
    traced values in the parent's call records, so ``Output.of``, automatic sums, ratios and
    helper methods that call children outside ``forward`` work unchanged. A child that cannot
    be recorded raises ``TraceError``, which makes the whole root a graph break: its leaves'
    call records are read by the parent's automatic sums and ``Output.of``, so a composite
    child cannot be replaced by an opaque node.
    """

    def __init__(self, graph, root):
        """Trace into ``graph``, naming inputs relative to ``root``."""
        self.graph = graph
        self.root = root
        self._inputs = {}
        self._parameters = {}
        self.limit_checks = []

    def child(self, module, inlets, supplied, parent):
        """Record one child call and return its ``ModuleResult`` of traced values.

        A stateful or pre-hooked leaf, and a leaf whose trace raises ``TraceError``, become one
        break node and the rest of the graph is kept; a composite child that cannot be
        recorded, or any child with an observer, raises ``TraceError`` instead.
        """
        _check_observers(module)
        reason = _unrecordable(module)
        mark = self._mark()
        try:
            if reason is not None:
                raise TraceError(f"{module.path}: {reason}")
            outlets, call = self.run(module, inlets, supplied, parent)
            outputs, inputs, records = call.outputs or {}, call.inputs, call.call_records
        except TraceError as error:
            if not module.is_leaf:
                raise
            self._rollback(mark)
            outlets, outputs, inputs = record_break(
                self.graph, module, inlets, supplied, outputs_enabled(), str(error)
            )
            records = []
        result = ModuleResult(
            outputs=Values(outputs, module._outputs),
            outlets=outlets,
            inlets=inlets,
            inputs=dict(inputs),
            children=dict(records),
            call_records=tuple(records),
            is_leaf=module.is_leaf,
        )
        parent.call_records.append((module._relative_path(parent.module), result))
        return result

    def _mark(self):
        return self.graph.mark(), dict(self._inputs), dict(self._parameters)

    def _rollback(self, mark):
        graph_mark, self._inputs, self._parameters = mark[0], mark[1], mark[2]
        self.graph.rollback(graph_mark)

    def run(self, module, inlets, supplied, parent):
        """Trace ``forward`` and the output step of ``module``; return its outlets and call."""
        call = _Call(
            module=module,
            inputs=self._call_inputs(module, supplied),
            outputs={} if outputs_enabled() else None,
            parent=parent,
            parameters=self._call_parameters(module),
            trace=self,
        )
        token = _current_call.set(call)
        try:
            outlets = Ports(_forward(module, inlets), path=module.path)
            if call.outputs is not None:
                self._trace_outputs(module, call, inlets, outlets)
            before = len(self.graph.checks)
            check_declared_limits(module, call)
            self.limit_checks.extend(self.graph.checks[before:])
        finally:
            _current_call.reset(token)
        return outlets, call

    def _prefix(self, module):
        """Return the path of ``module`` relative to the root; empty for the root itself."""
        if module is self.root:
            return ""
        return module.path.removeprefix(self.root.path + ".")

    def _call_inputs(self, module, supplied):
        """Return controls and boundaries: supplied values win, else one graph input each."""
        prefix = self._prefix(module)
        inputs = {}
        for role, declarations in (("control", module._controls), ("boundary", module._boundaries)):
            for name, declaration in declarations.items():
                if name in supplied:
                    inputs[name] = supplied[name]
                    continue
                if (module, name) not in self._inputs:
                    full = join_path(prefix, name)
                    self._inputs[module, name] = self.graph.input(full, role, declaration.unit)
                inputs[name] = self._inputs[module, name]
        return inputs

    def _call_parameters(self, module):
        """Return traced numeric parameters by name; other values stay as they are (guards)."""
        if module not in self._parameters:
            self._parameters[module] = _parameters(self.graph, module, self._prefix(module))
        return self._parameters[module]

    def _trace_outputs(self, module, call, inlets, outlets):
        """Trace the output step and classify each forward hook as part of the graph or observer.

        A marked observer is never called; a hook that writes no output is an observer too.
        Observers are replayed per row for the root only, so one on a child is a graph break.
        """
        module._compute_outputs(inlets, outlets)
        module._compute_formula_outputs(call)
        for hook in tuple(module._hooks.values()):
            if is_observer(hook):
                self._observe(module, hook)
                continue
            before = dict(call.outputs)
            try:
                hook(module, inlets, outlets)
            except TraceError as error:
                raise TraceError(f"{module.path}: forward hook {hook!r}: {error}") from error
            written = [
                name for name, value in call.outputs.items() if before.get(name) is not value
            ]
            if not written:
                self._observe(module, hook)
        module._check_outputs(call.outputs)

    def _observe(self, module, hook):
        if module is not self.root:
            raise TraceError(
                f"{module.path}: forward hook {hook!r} only reads and cannot be replayed on a "
                "child of a composite"
            )
        self.graph.observers.append(hook)


def _check_traceable(module):
    """Refuse what the root of a trace cannot be; each refusal is a graph break."""
    reasons = []
    if module.stateful:
        reasons.append("stateful (needs scan)")
    if not all(is_observer(hook) for hook in module._pre_hooks.values()):
        reasons.append("has forward pre-hooks")
    if runtime.get_precision() != "float64":
        reasons.append("runtime precision is not float64")
    if reasons:
        raise TraceError(f"{module.path}: cannot be traced: {'; '.join(reasons)}")


def _unrecordable(module):
    """Return why a child call cannot be recorded in the graph, or ``None``."""
    if module.stateful:
        return "stateful (needs scan)"
    if module._pre_hooks:
        return "has forward pre-hooks"
    return None


def _check_observers(module):
    """Refuse a child with an observer: it is replayed per row for the root only."""
    hooks = (*module._pre_hooks.values(), *module._hooks.values())
    if any(is_observer(hook) for hook in hooks):
        raise TraceError(
            f"{module.path}: observer hooks on a child of a composite cannot be replayed"
        )


def _inlet(graph, name, fluid):
    """Return the traced stream of one inlet: graph inputs for its fields, the fixed fluid."""
    fields = {field: graph.input(f"{name}.{field}", "inlet", unit) for field, unit in STREAM_FIELDS}
    return Stream(fluid=fluid, **fields)


def _parameters(graph, module, prefix):
    """Return traced numeric parameters by name; other values stay as they are (guards)."""
    parameters = {}
    for name, declaration in module._parameters.items():
        value = declaration.value
        shape = traced_shape(declaration)
        if shape is None:
            parameters[name] = value
            continue
        parameters[name] = graph.input(
            join_path(prefix, name), "parameter", declaration.unit, shape
        )
    return parameters


def traced_shape(declaration):
    """Return the graph-input shape of a parameter, or ``None`` when it is a plain value.

    A structural parameter and a non-numeric one are read as plain values and are cache guards.
    """
    if declaration.structural:
        return None
    return parameter_shape(declaration.value)


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
