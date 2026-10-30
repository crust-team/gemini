"""Run one module over whole time series: ``evaluate`` plus a raise, and the observer replay.

``run(module, inlets, inputs)`` is the prototype's stand-in for the engine integration. Inlets
are ``Stream`` objects whose fields are arrays over time (validated when built);
``inputs`` maps control and boundary names to arrays or scalars, and the module's persisted
values fill the rest. Parameters and constants come from the module and the graph. It is a thin
form over ``evaluate``: the graph (a root break when the module cannot be traced, its reason in
``Run.breaks``) is evaluated on the backend you name and the first failing row raises its
exception. Observer hooks are replayed per row after a traced run, pre-hooks first. The row
count is the longest array among the inlet fields and inputs, one without arrays.

``graph_feeds`` gives the value of every graph input and ``replay_row`` calls the observer hooks
of one row; the engine uses both with ``evaluate``.

``run_function(function, *args, **fixed)`` does the same for a plain function (a physics
function, a module's helper): the numeric positional arguments become graph inputs, the
function is traced once on them, and the graph is evaluated on the arguments, so an array
argument crosses ``where`` and ``check`` like a column of a run instead of raising at its first
failing row in the function body.
"""

import dataclasses
from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np

from gemini import backends, ops
from gemini.core.modules.module import _Call, _current_call
from gemini.graph.cache import GraphCache
from gemini.graph.evaluation import evaluate
from gemini.graph.graph import Graph
from gemini.graph.limits import certain
from gemini.graph.proxy import Proxy
from gemini.graph.tracer import STREAM_FIELDS


@dataclass
class Run:
    """Results of one run: output and outlet-field arrays, graph breaks and the graph used."""

    outputs: dict
    outlets: dict
    breaks: list
    graph: object


def run(module, inlets, inputs=None, *, backend="numpy", cache=None):
    """Evaluate ``module`` on every row of ``inlets`` and ``inputs`` and return a ``Run``."""
    inputs = dict(inputs or {})
    rows = _row_count(inlets, inputs)
    fluids = {name: inlets[name].fluid for name in module._inlets}
    graph = (cache or GraphCache()).graph(module, fluids)
    feeds = graph_feeds(graph, module, inlets, inputs)
    with backends.settings(backend=backend):
        evaluation = evaluate(graph, feeds, rows)
    _raise_first(evaluation)
    result = evaluation.result
    outlets = {
        port: {field: getattr(result.outlets[port], field) for field, _ in STREAM_FIELDS}
        for port in module._outlets
    }
    if graph.root is None:
        _replay_observers(graph, module, result, rows)
    breaks = [reason for _, reason in graph.breaks] if graph.root is not None else []
    return Run(outputs=dict(result.outputs.items()), outlets=outlets, breaks=breaks, graph=graph)


def _raise_first(evaluation):
    """Raise the exception of the first failed row of ``evaluation``, if any."""
    if evaluation.failed.any():
        raise evaluation.error(int(np.flatnonzero(evaluation.failed)[0]))


def _row_count(inlets, inputs):
    """Return the longest array among the inlet fields and inputs; one row if all are scalars."""
    sizes = [
        np.size(getattr(stream, field)) for stream in inlets.values() for field, _ in STREAM_FIELDS
    ]
    sizes += [np.size(value) for value in inputs.values()]
    return max(sizes, default=1)


def graph_feeds(graph, module, inlets, inputs):
    """Return the value of every graph input; ``inputs`` maps names to arrays or scalars.

    A control or boundary without a value (``None``, for an optional one) is NaN, like every
    value-dependent ``None`` in a graph. A parameter keeps the value it was given, so a message
    prints it as the plain path does (``2``, not ``2.0``). A root break takes only the inputs
    supplied: it reads the others from the module as any call does.
    """
    feeds = {}
    for name, stream in inlets.items():
        feeds |= {
            f"{name}.{field}": np.asarray(getattr(stream, field)) for field, _ in STREAM_FIELDS
        }
    for name in graph.by_role("control") | graph.by_role("boundary"):
        owner, local = _owner(module, name)
        if name in inputs:
            value = inputs[name]
        elif graph.root is None:
            value = owner._input_value(local)
        else:
            continue
        feeds[name] = np.asarray(np.nan if value is None else value)
    for name in graph.by_role("parameter"):
        owner, local = _owner(module, name)
        feeds[name] = np.asarray(owner._parameter_value(local))
    for name, constant in graph.constants.items():
        feeds[name] = constant.value
    return feeds


def _owner(module, name):
    """Return the module that owns the graph input ``name`` and the input's local name."""
    path, _, local = name.rpartition(".")
    return (module.get_submodule(path) if path else module), local


def _replay_observers(graph, module, result, rows):
    """Call every observer hook once per row with that row's inlets, outlets and outputs."""
    for index in range(rows if graph.observers or graph.pre_observers else 0):
        row = result.row(index)
        replay_row(graph, module, row.inlets, row.outlets, row.inputs, dict(row.outputs.items()))


def replay_row(graph, module, inlets, outlets, inputs, outputs):
    """Call the observer hooks of ``graph`` for one row: pre-hooks first, then forward hooks.

    The hooks run inside a call record holding the row's ``inputs`` and ``outputs``, so
    ``module.<control>`` and ``module.<output>`` read that row.
    """
    call = _Call(module=module, inputs=inputs, outputs=outputs, parent=None)
    token = _current_call.set(call)
    try:
        for pre_hook in graph.pre_observers:
            pre_hook(module, inlets)
        for hook in graph.observers:
            hook(module, inlets, outlets)
    finally:
        _current_call.reset(token)


def run_function(function, *args, backend="numpy", **fixed):
    """Trace ``function(*args, **fixed)`` with its numeric arguments as inputs and evaluate it.

    A float, a NumPy float or a float array among ``args`` is a graph input named
    ``arg<index>``; everything else (integers, flags, text, ``None``, lists, tuples) and every
    keyword in ``fixed`` is passed as it is, as structure. The result has the structure of
    what ``function`` returns (a number, tuple, list, dict or frozen dataclass) with arrays of
    one value per row in place of numbers. A failing ``check`` that reaches the result raises
    the class and message of the first failing row, and one in a branch ``where`` does not
    select does not.
    """
    graph = Graph(function.__name__)
    traced = [_input(graph, index, arg) for index, arg in enumerate(args)]
    with ops.scope.tracing(graph):
        result = function(*(proxy for proxy, _ in traced), **fixed)
    leaves = _leaves(result)
    for name, leaf in leaves.items():
        graph.output(name, leaf)
    certain(graph, graph.unframed)
    feeds = {
        f"arg{index}": np.asarray(arg)
        for index, (proxy, arg) in enumerate(traced)
        if isinstance(proxy, Proxy)
    }
    feeds |= {name: constant.value for name, constant in graph.constants.items()}
    rows = max([np.size(value) for value in feeds.values()], default=1)
    with backends.settings(backend=backend):
        evaluation = evaluate(graph, feeds, rows)
    _raise_first(evaluation)
    scalar = all(np.ndim(value) == 0 for value in feeds.values())
    values = {
        name: evaluation.output(name)[0] if scalar else evaluation.output(name)
        for name in graph.outputs
    }
    return _rebuilt(result, values)


def _input(graph, index, arg):
    """Return ``(traced value, argument)``; a numeric argument becomes a graph input."""
    numeric = isinstance(arg, (float, np.floating)) or (
        isinstance(arg, np.ndarray) and arg.dtype.kind == "f"
    )
    if not numeric:
        return arg, arg
    return graph.input(f"arg{index}", "control"), arg


def _leaves(result, prefix="result"):
    """Return the traced leaves of ``result`` by path name."""
    if isinstance(result, (tuple, list)):
        items = enumerate(result)
    elif isinstance(result, Mapping):
        items = result.items()
    elif dataclasses.is_dataclass(result) and not isinstance(result, type):
        items = ((field.name, getattr(result, field.name)) for field in dataclasses.fields(result))
    else:
        return {prefix: result}
    leaves = {}
    for key, item in items:
        leaves |= _leaves(item, f"{prefix}.{key}")
    return leaves


def _rebuilt(result, values, prefix="result"):
    """Return ``result`` with each leaf replaced by its evaluated value."""
    if isinstance(result, (tuple, list)):
        items = [_rebuilt(item, values, f"{prefix}.{index}") for index, item in enumerate(result)]
        return type(result)(items)
    if isinstance(result, Mapping):
        return {key: _rebuilt(item, values, f"{prefix}.{key}") for key, item in result.items()}
    if dataclasses.is_dataclass(result) and not isinstance(result, type):
        changes = {
            field.name: _rebuilt(getattr(result, field.name), values, f"{prefix}.{field.name}")
            for field in dataclasses.fields(result)
        }
        return dataclasses.replace(result, **changes)
    return values[prefix]
