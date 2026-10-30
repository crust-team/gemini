"""``Interpreter``: evaluate a graph on one backend, then raise the errors that reach an output.

The value pass runs every node in creation order on the backend (missing ops fall back to
NumPy). The error pass then gives every node the per-row error code of its operands and of the
checks guarding it (``0`` means no error; of several, the lowest code, the check that ran first,
wins), except that ``where`` keeps only the code of the branch it selected on each row. The
first row whose code reaches an output raises the check's ``gm.errors`` class with the message
of the untraced path, noted with the physics source line of the check. A break node runs its
module row by row; a failed row has the code of the node's check and its exception is
re-raised.
"""

import numpy as np

from gemini import backends
from gemini.errors import CallError
from gemini.graph.breaks import evaluate_break
from gemini.graph.node import Node
from gemini.graph.proxy import Proxy
from gemini.ops.check import failure


class Interpreter:
    """Run one graph on one backend."""

    def __init__(self, graph, backend):
        """Prepare to run ``graph`` on the backend object ``backend``."""
        self.graph = graph
        self.backend = backend

    def run(self, feeds):
        """Return every graph output by name for the input values ``feeds``."""
        missing = [name for name in self.graph.inputs if name not in feeds]
        if missing:
            raise CallError(f"{self.graph.module_path}: graph inputs without a value: {missing}")
        values = {}
        for node in self.graph.nodes:
            values[node] = self._evaluate(node, values, feeds)
        errors = self._errors(values)
        outputs = {name: _value(operand, values) for name, operand in self.graph.outputs.items()}
        self._raise_reached(errors, values)
        return outputs

    def _evaluate(self, node, values, feeds):
        if node.op == "input":
            return feeds[node.name]
        operands = [_value(operand, values) for operand in node.operands]
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

    def _raise_reached(self, errors, values):
        """Raise the error of the first row whose code reaches a graph output."""
        code = _first(errors.get(operand) for operand in self.graph.outputs.values())
        if code is None:
            return
        codes = np.atleast_1d(code)
        row = int(np.flatnonzero(codes)[0])
        check = self.graph.checks[int(codes[row]) - 1]
        if "break" in check.attributes:
            raise values[check.attributes["break"]].exceptions[row]
        message_values = {
            name: _value(value.node if isinstance(value, Proxy) else value, values)
            for name, value in check.attributes["values"].items()
        }
        error = failure(check.attributes["error"], check.attributes["message"], message_values, row)
        error.add_note(f"raised by the check at {check.source}")
        raise error


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
