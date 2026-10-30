"""Run one module over whole time series: one traced call, or row by row on a graph break.

``run(module, inlets, inputs)`` is the prototype's stand-in for the engine integration. Inlets
are ``Stream`` objects whose fields are arrays over time (validated when built);
``inputs`` maps control and boundary names to arrays or scalars, and the module's persisted
values fill the rest. Parameters and constants come from the module and the graph. A module
that cannot be traced runs untraced, one call per row, with the same results, and the reason
is reported in ``Run.breaks``. Observer hooks are replayed per row after a traced run, pre-hooks
first. The row count is the longest array among the inlet fields and inputs, one without arrays.
"""

from dataclasses import dataclass

import numpy as np

from gemini import backends
from gemini.core.modules.module import _Call, _current_call
from gemini.core.types.flows import Stream
from gemini.core.types.ports import Ports
from gemini.errors import TraceError
from gemini.graph.cache import GraphCache
from gemini.graph.interpreter import Interpreter
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
    try:
        graph = (cache or GraphCache()).graph(module, fluids)
    except TraceError as error:
        return _untraced(module, inlets, inputs, rows, str(error))
    values = _evaluate(graph, graph_feeds(graph, module, inlets, inputs), backend, rows)
    outputs = _stacked_vectors(
        graph,
        {
            name.removeprefix("outputs."): value
            for name, value in values.items()
            if name.startswith("outputs.")
        },
    )
    outlets = {
        port: {field: values[f"outlets.{port}.{field}"] for field, _ in STREAM_FIELDS}
        for port in module._outlets
    }
    _replay_observers(graph, module, inlets, inputs, outputs, outlets, rows)
    return Run(outputs=outputs, outlets=outlets, breaks=[], graph=graph)


def _row_count(inlets, inputs):
    """Return the longest array among the inlet fields and inputs; one row if all are scalars."""
    sizes = [
        np.size(getattr(stream, field)) for stream in inlets.values() for field, _ in STREAM_FIELDS
    ]
    sizes += [np.size(value) for value in inputs.values()]
    return max(sizes, default=1)


def _evaluate(graph, feeds, backend, rows):
    """Return every graph output as an array of ``rows``: in one call, or per row in Python."""
    interpreter = Interpreter(graph, backends.get(backend))
    if backend != "python":
        values = interpreter.run(feeds)
        return {name: np.broadcast_to(value, (rows,)) for name, value in values.items()}
    per_row = [interpreter.run(_row_feeds(graph, feeds, row)) for row in range(rows)]
    return {name: np.array([values[name] for values in per_row]) for name in graph.outputs}


def _row_feeds(graph, feeds, row):
    """Return the Python scalars of one row; vector parameters become Python lists."""
    return {
        name: np.asarray(value).tolist() if graph.inputs[name].shape else _row(value, row)
        for name, value in feeds.items()
    }


def graph_feeds(graph, module, inlets, inputs):
    """Return the value of every graph input; ``inputs`` maps names to arrays or scalars."""
    feeds = {}
    for name, stream in inlets.items():
        feeds |= {
            f"{name}.{field}": np.asarray(getattr(stream, field)) for field, _ in STREAM_FIELDS
        }
    for name in graph.by_role("control") | graph.by_role("boundary"):
        owner, local = _owner(module, name)
        feeds[name] = np.asarray(inputs[name] if name in inputs else owner._input_value(local))
    for name in graph.by_role("parameter"):
        owner, local = _owner(module, name)
        feeds[name] = np.asarray(owner._parameter_value(local), dtype=float)
    for name, constant in graph.constants.items():
        feeds[name] = constant.value
    return feeds


def _stacked_vectors(graph, outputs):
    """Replace the items of every list-valued output by one array of shape ``(rows, length)``."""
    for name, length in graph.vectors.items():
        key = name.removeprefix("outputs.")
        items = [outputs.pop(f"{key}[{index}]") for index in range(length)]
        outputs[key] = np.stack(items, axis=1)
    return outputs


def _owner(module, name):
    """Return the module that owns the graph input ``name`` and the input's local name."""
    path, _, local = name.rpartition(".")
    return (module.get_submodule(path) if path else module), local


def _row(value, row):
    array = np.asarray(value)
    return array[row].item() if array.ndim else array.item()


def _row_streams(inlets, row):
    return {
        name: Stream(
            m_dot=_row(state.m_dot, row),
            T=_row(state.T, row),
            p=_row(state.p, row),
            fluid=state.fluid,
        )
        for name, state in inlets.items()
    }


def _untraced(module, inlets, inputs, rows, reason):
    """Run ``module`` untraced, one call per row, and stack its results like a traced run."""
    results = []
    for row in range(rows):
        row_inputs = {name: _row(value, row) for name, value in inputs.items()}
        results.append(module(**_row_streams(inlets, row), **row_inputs))
    outputs = {name: np.array([r.outputs[name] for r in results]) for name in results[0].outputs}
    outlets = {
        port: {
            field: np.array([getattr(r.outlets[port], field) for r in results])
            for field, _ in STREAM_FIELDS
        }
        for port in module._outlets
    }
    return Run(outputs=outputs, outlets=outlets, breaks=[reason], graph=None)


def _replay_observers(graph, module, inlets, inputs, outputs, outlets, rows):
    """Call every observer hook once per row with that row's inlets, outlets and outputs."""
    for row in range(rows if graph.observers or graph.pre_observers else 0):
        row_outlets = Ports(
            {
                port: Stream(
                    **{field: _row(value, row) for field, value in fields.items()},
                    fluid=graph.outlet_fluids[port],
                )
                for port, fields in outlets.items()
            },
            path=module.path,
        )
        replay_row(
            graph,
            module,
            Ports(_row_streams(inlets, row), path=module.path),
            row_outlets,
            module._resolve_inputs({k: _row(v, row) for k, v in inputs.items()}),
            {name: _row(value, row) for name, value in outputs.items()},
        )


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
