"""One node of a computation graph: a graph input or one op applied to earlier nodes."""

import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from gemini.types import flows
from gemini.types.flows import Stream

_TRACING_PACKAGES = tuple(
    str(Path(__file__).parents[1] / package) for package in ("graph", "ops", "backends")
)


STREAM_FIELDS = tuple(zip(flows.STREAM_FIELDS, ("kg/s", "K", "Pa")))
"""Stream fields of every inlet and outlet in the graph, with their units."""


def row_item(value, row):
    """Return row ``row`` of a column as a plain Python value; a scalar holds for every row."""
    array = np.asarray(value)
    return array[row].item() if array.ndim else array.item()


def stack_column(values):
    """Return the values of one position over the rows as an array; ``None`` is NaN."""
    return np.array([np.nan if value is None else value for value in values])


def row_streams(fluids, value):
    """Return the inlet streams of one row: ``value(port, field)`` for each field of each port."""
    return {
        port: Stream(**{field: value(port, field) for field, _ in STREAM_FIELDS}, fluid=fluid)
        for port, fluid in fluids.items()
    }


@dataclass(eq=False, slots=True)
class Node:
    """A graph input (``op == "input"``) or one op applied to ``operands``.

    ``operands`` holds earlier nodes and literal numbers. Inputs carry a ``name``, a ``role``
    (``inlet``, ``control``, ``boundary``, ``parameter`` or ``constant``), a ``unit`` and the
    ``shape`` of one row (``()`` or ``(n,)`` for a vector parameter). A ``check`` node carries
    its error class, message and message values in ``attributes`` and its error ``code``.
    ``guards`` lists the check nodes whose errors travel with this node's value. ``source`` is
    the file and line of the physics code that created the node.
    """

    index: int
    op: str
    kind: str
    operands: tuple = ()
    name: str | None = None
    role: str | None = None
    unit: str | None = None
    shape: tuple = ()
    attributes: dict | None = None
    code: int = 0
    guards: list = field(default_factory=list)
    source: str = ""

    def label(self):
        """Return ``%index`` with the input name, for graph listings."""
        return f"%{self.index}" + (f"<{self.name}>" if self.name else "")


def caller_source():
    """Return ``file:line`` of the innermost frame outside the tracing packages."""
    frame = sys._getframe(1)
    while frame is not None and frame.f_code.co_filename.startswith(_TRACING_PACKAGES):
        frame = frame.f_back
    if frame is None:
        return ""
    return f"{frame.f_code.co_filename}:{frame.f_lineno}"
