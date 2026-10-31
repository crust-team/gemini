"""The exception of one failing row of a graph: the one builder of the exact error.

``RowView`` reads the value of a node at one row (a parameter prints as it was given, ``2`` and
not ``2.0``). ``row_error`` turns the error code that reaches an output on that row into the
exception of a plain call: the check's class with its message filled from the row's values
by ``failure``; for a declared bound the text of ``Declaration.validate``; for a break node the
exception the module raised. The exception is noted with the source line of the check.
"""

import numpy as np

from gemini.compiler.graph.node import Node
from gemini.compiler.graph.proxy import Proxy
from gemini.ops.check import failure


class RowView:
    """The values of a graph at one row.

    ``values`` maps nodes to their values (arrays over rows, or scalars when ``row`` is ``0``
    and the values are those of one row), ``feeds`` are the values the graph was fed.
    """

    def __init__(self, values, row, feeds):
        """Read ``row`` of ``values``."""
        self.values, self.row, self.feeds = values, row, feeds

    def value(self, operand):
        """Return the plain Python value of a traced value, a node, a list of them or a literal."""
        if isinstance(operand, (list, tuple)):
            return [self.value(item) for item in operand]
        if isinstance(operand, Proxy):
            operand = operand.node
        if not isinstance(operand, Node):
            return operand
        if operand.role == "parameter" and operand.name in self.feeds:
            return np.asarray(self.feeds[operand.name]).tolist()
        value = self.values[operand]
        if isinstance(value, np.ndarray) and value.ndim and not operand.shape:
            return value[self.row].tolist()
        if isinstance(value, np.generic):
            return value.item()
        return value

    def exception(self, node):
        """Return the exception a break node recorded for this row."""
        return self.values[node].exceptions[self.row]


def row_error(check, view):
    """Return the exception of ``check`` at the row of ``view``."""
    attributes = check.attributes
    if "break" in attributes:
        return view.exception(attributes["break"])
    values = {name: view.value(value) for name, value in attributes["values"].items()}
    error = _declared(values) or failure(
        attributes["error"], attributes["message"], values, 0, attributes["code"]
    )
    error.add_note(f"raised by the check at {check.source}")
    return error


def _declared(values):
    """Return the error ``Declaration.validate`` raises for the whole value, else ``None``."""
    declaration = values.get("declaration")
    if declaration is None:
        return None
    whole = values["whole"]
    if declaration.accepts_none():
        whole = _nullable(whole)
    try:
        declaration.validate(whole)
    except Exception as error:
        return error
    return None


def _nullable(whole):
    """Return ``whole`` with NaN as ``None``, the way a declared ``X | None`` is stored."""
    if isinstance(whole, list):
        return [_nullable(item) for item in whole]
    return None if whole != whole else whole
