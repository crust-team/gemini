"""``evaluate``: one evaluation of a graph over the rows of a chunk, on either backend.

``evaluate(graph, feeds, rows, context)`` is used by ``gemini.compiler.graph.run`` and the engine.
The backend is the one of ``gm.runtime.settings(backend=...)``, NumPy by default: NumPy
evaluates the graph in one pass over arrays of ``rows``; Python evaluates the same graph row by
row with Python floats and lists and stacks the nodes into the same arrays. Both go through the
same ``Interpreter`` and the same reached-code computation (``Interpreter.reached``). A root
break graph calls the real module row by row (see ``rootbreak``). ``feeds`` maps graph inputs
to arrays over the rows or scalars, which broadcast; ``context`` may hold ``dt`` and ``states``
for a stepped root break.

An ``Evaluation`` holds ``result``, the ``ModuleResult`` tree of the trace mapped to arrays of
``rows`` (children included; a root break stacks its real rows): a literal broadcasts, a list
of traced values is an array of shape ``(rows, n)``, ``None`` is NaN (``ModuleResult.row`` reads
it back as ``None`` for a declared ``X | None``) and an output has the dtype its declaration
gives on the plain path. ``failed`` marks the rows with an error reaching an output and
``error(row)`` is the exception of that row. ``states`` are the states after a stepped break.
"""

import dataclasses

import numpy as np

from gemini.compiler.graph.failures import RowView, row_error
from gemini.compiler.graph.interpreter import Interpreter
from gemini.compiler.graph.node import Node, stack_column
from gemini.compiler.graph.proxy import Proxy
from gemini.compiler.graph.rootbreak import run_rows, stacked
from gemini.ops import Constant, kernels
from gemini.types.results import Values

DTYPES = {"number": float, "boolean": bool, "integer": np.int64}
"""The NumPy type of an output by the JSON type of its declaration."""


class Evaluation:
    """The result of evaluating a graph over ``rows`` rows."""

    def __init__(self, graph, rows, failed, result, errors, states=None, convert=None):
        """Keep the mapped ``result``, the ``failed`` mask and ``errors``, a function of a row."""
        self.graph = graph
        self.rows = rows
        self.failed = failed
        self.result = result
        self.states = states
        self._errors = errors
        self._convert = convert

    def error(self, row):
        """Return the exception of a failed ``row``: the check's class with its exact message."""
        return self._errors(row)

    def raise_first(self):
        """Raise the exception of the first failed row, if any."""
        if self.failed.any():
            raise self._errors(int(np.flatnonzero(self.failed)[0]))

    def output(self, name):
        """Return the array of the graph output ``outputs.<name>`` or ``outlets.<port>.<field>``."""
        return self._convert(self.graph.outputs[name])


def evaluate(graph, feeds, rows, context=None):
    """Evaluate ``graph`` on ``feeds`` over ``rows`` rows and return an ``Evaluation``."""
    context = context or {}
    with np.errstate(all="ignore"):
        if graph.root is not None:
            return _root_evaluation(graph, feeds, rows, context)
        if kernels.forced_name() == "python":
            return _python_evaluation(graph, feeds, rows)
        return _numpy_evaluation(graph, feeds, rows)


def _numpy_evaluation(graph, feeds, rows):
    interpreter = Interpreter(graph, kernels.get("numpy"))
    values, errors = interpreter.execute(feeds)
    codes = interpreter.reached(errors)

    def column(node):
        shape = (rows, *node.shape)
        return np.broadcast_to(np.asarray(values[node]), shape)

    def error(row):
        return row_error(graph.checks[int(codes[row]) - 1], RowView(values, row, feeds))

    return _assembled(graph, rows, codes, column, error)


def _python_evaluation(graph, feeds, rows):
    interpreter = Interpreter(graph, kernels.get("python"))
    row_values, row_codes = [], []
    for row in range(rows):
        values, errors = interpreter.execute(_row_feeds(graph, feeds, rows, row))
        codes = interpreter.reached(errors)
        row_values.append(values)
        row_codes.append(0 if codes is None else int(codes[0]))
    codes = np.array(row_codes, dtype=int)

    def column(node):
        return stack_column([values[node] for values in row_values])

    def error(row):
        return row_error(graph.checks[codes[row] - 1], RowView(row_values[row], 0, feeds))

    return _assembled(graph, rows, codes, column, error)


def _row_feeds(graph, feeds, rows, row):
    """Return the Python scalars of one row; a vector parameter is a Python list."""
    values = {}
    for name, value in feeds.items():
        shape = graph.inputs[name].shape
        values[name] = np.broadcast_to(np.asarray(value), (rows, *shape))[row].tolist()
    return values


def _assembled(graph, rows, codes, column, error):
    """Return the ``Evaluation`` of per-node ``column`` values and reached ``codes``."""
    failed = np.zeros(rows, dtype=bool) if codes is None else codes != 0
    convert = _converter(column, rows)
    result = None if graph.result is None else _typed(graph.result.mapped(convert))
    return Evaluation(graph, rows, failed, result, error, convert=convert)


def _converter(column, rows):
    """Return the function that maps a traced value, a literal or a list of them to an array."""

    def convert(value):
        if isinstance(value, Node):
            return column(value)
        if isinstance(value, Proxy):
            return column(value.node)
        if isinstance(value, (list, tuple)):
            items = [convert(item) for item in value]
            return np.stack(items, axis=1) if items else np.empty((rows, 0))
        if isinstance(value, Constant):
            value = value.value
        if value is None:
            return np.full(rows, np.nan)
        if isinstance(value, (bool, int, float, np.number, np.bool_)):
            return np.full(rows, value)
        return value

    return convert


def _root_evaluation(graph, feeds, rows, context):
    results, errors, states = run_rows(graph, feeds, rows, context)
    failed = np.ones(rows, dtype=bool)
    failed[list(results)] = False
    result = stacked(results, rows)
    return Evaluation(
        graph,
        rows,
        failed,
        None if result is None else _typed(result),
        errors.__getitem__,
        states,
    )


def _typed(result, done=None):
    """Return ``result`` with the outputs in the dtype their declarations have on the plain path."""
    done = {} if done is None else done
    if id(result) in done:
        return done[id(result)]
    declarations = result.outputs._declarations
    values = {name: _cast(value, declarations.get(name)) for name, value in result.outputs.items()}
    typed = dataclasses.replace(
        result,
        outputs=Values._trusted(values, declarations),
        children={name: _typed(child, done) for name, child in result.children.items()},
        call_records=tuple((name, _typed(child, done)) for name, child in result.call_records),
    )
    done[id(result)] = typed
    return typed


def _cast(value, declaration):
    if declaration is None or not isinstance(value, np.ndarray):
        return value
    kind = DTYPES.get(declaration.value_type())
    if kind is None or value.dtype.kind not in "biuf":
        return value
    return value.astype(kind)
