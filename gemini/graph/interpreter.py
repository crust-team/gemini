"""``Interpreter``: evaluate a graph on one backend and find the errors that reach an output.

The value pass runs every node in creation order on the backend (missing ops fall back to
NumPy; a ``None`` branch of ``where`` is NaN, as it is on arrays). The error pass then gives
every node the per-row error code of its operands and of the checks guarding it (``0`` means
no error; of several, the lowest code, the check that ran first, wins), except that ``where`` keeps only the code of the branch it selected on each row.
The first row whose code reaches an output raises, in ``run``, the exception ``failures.row_error``
builds. ``evaluation.evaluate`` is the form that keeps every row. A break node runs its module
row by row; a failed row has the code of the node's check and its exception is re-raised.
"""

import math

import numpy as np

from gemini import backends
from gemini.errors import CallError, TraceError
from gemini.graph.breaks import evaluate_break
from gemini.graph.failures import RowView, row_error
from gemini.graph.node import Node


class Interpreter:
    """Run one graph on one backend."""

    def __init__(self, graph, backend):
        """Prepare to run ``graph`` on the backend object ``backend``.

        A root break has no nodes: ``evaluate`` calls its module, so it is refused here with
        its reason.
        """
        if graph.root is not None:
            raise TraceError(graph.breaks[0][1])
        self.graph = graph
        self.backend = backend

    def run(self, feeds):
        """Return every graph output by name for the input values ``feeds``.

        The first row whose error reaches an output raises the exception ``failures.row_error``
        builds for it: ``evaluation.evaluate`` plus a raise.
        """
        values, errors = self.execute(feeds)
        outputs = {name: _value(operand, values) for name, operand in self.graph.outputs.items()}
        codes = self.reached(errors)
        if codes is None:
            return outputs
        row = int(np.flatnonzero(codes)[0])
        check = self.graph.checks[int(codes[row]) - 1]
        raise row_error(check, RowView(values, row, feeds))

    def evaluate(self, feeds):
        """Return the outputs and a boolean array of the rows whose error reaches an output.

        Nothing is raised. The mask is ``None`` when no row failed.
        """
        values, errors = self.execute(feeds)
        outputs = {name: _value(operand, values) for name, operand in self.graph.outputs.items()}
        codes = self.reached(errors)
        return outputs, None if codes is None else codes != 0

    def execute(self, feeds):
        """Run the value pass, then the error pass; return the node values and error codes."""
        missing = [name for name in self.graph.inputs if name not in feeds]
        if missing:
            raise CallError(f"{self.graph.module_path}: graph inputs without a value: {missing}")
        values = {}
        for node in self.graph.nodes:
            values[node] = self._evaluate(node, values, feeds)
        return values, self._errors(values)

    def reached(self, errors):
        """Return the error code reaching an output on each row, or ``None`` if none does.

        This is the one reached-code computation: the lowest code wins over all outputs.
        """
        code = _first(errors.get(operand) for operand in self.graph.outputs.values())
        if code is None:
            return None
        return np.atleast_1d(code)

    def _evaluate(self, node, values, feeds):
        if node.op == "input":
            return _fed(node, feeds[node.name])
        operands = [_value(operand, values) for operand in node.operands]
        if node.op == "where":
            operands = [math.nan if operand is None else operand for operand in operands]
        if node.kind == "break":
            return _break_value(node, operands)
        method = backends.implementation(self.backend, node.op)
        if node.op == "check":
            return method(operands[0], node.code)
        if node.kind == "solver":
            return method(*operands, **node.attributes)
        return method(*operands)

    def _errors(self, values):
        """Return the error codes of every node that some check reaches."""
        errors = {}
        for node in self.graph.nodes:
            if node.op == "where":
                code = _where_code(node, values, errors)
            else:
                code = _first(errors.get(operand) for operand in node.operands)
            code = _first([code] + [values[check] for check in node.guards])
            if code is not None and np.any(code):
                errors[node] = code
        return errors


def _fed(node, value):
    """Return the value of an input node; a parameter is a float, whatever it was given as."""
    if node.role != "parameter":
        return value
    if isinstance(value, np.ndarray):
        return value.astype(float)
    if isinstance(value, list):
        return [float(item) for item in value]
    return float(value)


def _break_value(node, operands):
    """Run a break node, or select one column of the result of the one it belongs to."""
    if node.op == "break":
        return evaluate_break(node, operands)
    return operands[0].column(node.attributes["key"])


def _value(operand, values):
    return values[operand] if isinstance(operand, Node) else operand


def _first(codes):
    """Combine error codes per row: ``0`` is no error and the lowest nonzero code wins."""
    combined = None
    for code in codes:
        if code is None:
            continue
        if combined is None:
            combined = code
            continue
        keep = (combined != 0) & ((code == 0) | (combined < code))
        combined = np.where(keep, combined, code)
    return combined


def _where_code(node, values, errors):
    """Return the condition's code combined with the code of the selected branch per row."""
    condition, if_true, if_false = node.operands
    branches = [errors.get(if_true), errors.get(if_false)]
    selected = None
    if any(code is not None for code in branches):
        true_code, false_code = (0 if code is None else code for code in branches)
        selected = np.where(_value(condition, values), true_code, false_code)
    return _first([errors.get(condition), selected])
