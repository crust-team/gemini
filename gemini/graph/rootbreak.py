"""Root break: a module that cannot be traced is called for real, row by row.

``root_break_graph`` gives a graph without nodes whose ``root`` is the module. Its inputs are
the fields of the inlets and every control and boundary of the tree, named as a traced graph
names them, so ``graph_feeds`` and the engine feed it like any graph. ``run_rows`` evaluates
it: for each row it builds the inlet streams, applies the controls and boundaries it was given
(validated, and put back afterwards: persisting inputs is the caller's business) and calls
``module(streams)``, or ``module.step(state, dt, streams)`` for a stepped break, so the state
tree, the ``_Step`` record and "called twice" stay in ``Module.step``, the one implementation.
A row that raises is a failed row with that exception; the states carry over the failed row
unchanged. The rows are real ``ModuleResult`` trees, so children and
the combinations of a plant are exact; ``stacked`` joins them into one tree of arrays.
"""

from contextlib import contextmanager

import numpy as np

from gemini import backends
from gemini.graph.graph import Graph
from gemini.graph.node import STREAM_FIELDS, row_item, row_streams, stack_column

_ABSENT = object()


def root_break_graph(module, fluids, stepped, reason):
    """Return the graph of a root break of ``module`` for the inlet ``fluids``.

    ``stepped`` is kept only when a module of the tree is stateful: otherwise ``Module.step``
    has nothing to advance and the break is a plain call.
    """
    graph = Graph(module.path)
    for port in module._fed_inlets():
        for field, unit in STREAM_FIELDS:
            graph.input(f"{port}.{field}", "inlet", unit)
    for role, declarations in (("control", module.controls()), ("boundary", module.boundaries())):
        for path, declaration in declarations.items():
            graph.input(path, role, declaration.unit)
    graph.root = module
    graph.stepped = stepped and any(member.stateful for member in module.modules())
    graph.inlet_fluids = {port: fluids[port] for port in module._fed_inlets()}
    graph.breaks.append((module.path, reason))
    return graph


def run_rows(graph, feeds, rows, context):
    """Call the module of a root break on every row; return results, errors and states.

    ``results`` and ``errors`` map the row index to the ``ModuleResult`` or the exception of
    that row. ``context`` may hold ``dt`` (seconds, one number or one per row) and ``states``
    (the state tree a stepped break starts from, ``None`` for the initial states); the returned
    states are those after the last row that did not fail.
    """
    state = context.get("states")
    steps = np.broadcast_to(np.asarray(context.get("dt", np.nan), dtype=float), (rows,))
    results, errors = {}, {}
    for row in range(rows):
        try:
            result, state = _call_row(graph, feeds, row, float(steps[row]), state)
        except Exception as error:
            errors[row] = error
            continue
        results[row] = result
    return results, errors, state if graph.stepped else None


def _call_row(graph, feeds, row, dt, state):
    """Return the result of one row and the states after it."""
    module = graph.root
    streams = row_streams(
        graph.inlet_fluids, lambda port, field: row_item(feeds[f"{port}.{field}"], row)
    )
    fields = graph.by_role("inlet")
    inputs = {name: row_item(value, row) for name, value in feeds.items() if name not in fields}
    with backends.settings(backend=None), _applied(module, inputs):
        if not graph.stepped:
            return module(streams), state
        next_state, result = module.step(state, dt, streams)
        return result, next_state


@contextmanager
def _applied(module, inputs):
    """Hold ``inputs`` (controls and boundaries by dotted path) on their owners for one call.

    A value is validated as ``Module._set_inputs`` does; NaN is the ``None`` of a declared
    ``X | None``. The previous values are put back afterwards.
    """
    declarations = module.inputs()
    saved = []
    try:
        for path, value in inputs.items():
            declaration = declarations[path]
            if declaration.accepts_none() and value != value:
                value = None
            store = declaration.owner._input_values
            saved.append((store, declaration.name, store.get(declaration.name, _ABSENT)))
            store[declaration.name] = declaration.validate(value)
        yield
    finally:
        for store, name, previous in reversed(saved):
            if previous is _ABSENT:
                store.pop(name, None)
            else:
                store[name] = previous


def stacked(results, rows):
    """Return the results of the ok rows as one tree of arrays of ``rows``, or ``None``.

    The tree has the structure of the first ok row; a failed row is NaN. Every row of a break
    has the structure of the first: the same children, outputs and streams.
    """
    if not results:
        return None
    first = next(iter(results.values()))
    columns = {row: _flatten(result) for row, result in results.items()}
    position = iter(range(len(columns[next(iter(columns))])))

    def stack(_):
        index = next(position)
        missing = _missing(next(iter(columns.values()))[index])
        return stack_column(
            [columns[row][index] if row in columns else missing for row in range(rows)]
        )

    return first.mapped(stack)


def _missing(value):
    """Return what a failed row holds in a column of ``value``: NaN, or a list of them."""
    return [np.nan] * len(value) if isinstance(value, (list, tuple)) else np.nan


def _flatten(result):
    """Return every value of a result tree in the order ``ModuleResult.mapped`` visits them."""
    values = []

    def visit(value):
        values.append(value)
        return value

    result.mapped(visit)
    return values
