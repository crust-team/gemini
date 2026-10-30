"""``Proxy``: a traced value that records every op applied to it as a graph node.

A proxy has no number, so anything that needs one during the trace raises ``TraceError``:
``if``/``and``/``or`` on a traced value (``bool``), ``float()``, ``int()``, NumPy conversion and
string formatting. ``TraceError`` makes the module a graph break; physics written with
``gemini.ops.where``, ``check`` and ``logical_and`` never needs them.
"""

from gemini.graph.errors import TraceError
from gemini.ops import Operators, Symbolic, dispatch


class Proxy(Symbolic, Operators):
    """A traced value: one graph node and the graph that owns it."""

    __slots__ = ("node", "graph")
    __hash__ = object.__hash__

    def __init__(self, node, graph):
        """Wrap ``node`` of ``graph``."""
        self.node = node
        self.graph = graph

    def record(self, definition, operands, attributes=None):
        """Record one op in this proxy's graph."""
        return self.graph.record(definition, operands, attributes)

    def __eq__(self, other):
        """Return the traced ``self == other``."""
        return dispatch("eq", self, other)

    def __ne__(self, other):
        """Return the traced ``self != other``."""
        return dispatch("ne", self, other)

    def __and__(self, other):
        """Return the traced ``logical_and(self, other)``."""
        return dispatch("logical_and", self, other)

    def __rand__(self, other):
        """Return the traced ``logical_and(other, self)``."""
        return dispatch("logical_and", other, self)

    def __or__(self, other):
        """Return the traced ``logical_or(self, other)``."""
        return dispatch("logical_or", self, other)

    def __ror__(self, other):
        """Return the traced ``logical_or(other, self)``."""
        return dispatch("logical_or", other, self)

    def __invert__(self):
        """Return the traced ``logical_not(self)``."""
        return dispatch("logical_not", self)

    def __getitem__(self, index):
        """Return item ``index`` of a traced vector."""
        return dispatch("getitem", self, index)

    def __len__(self):
        """Return the length of a traced vector."""
        if not self.node.shape:
            raise self._untraceable("len()")
        return self.node.shape[0]

    def __iter__(self):
        """Iterate the items of a traced vector of known length."""
        return (self[index] for index in range(len(self)))

    def __bool__(self):
        """Refuse a truth value: value-dependent control flow cannot be traced."""
        raise self._untraceable("a truth value (if, and, or, chained comparison)")

    def __float__(self):
        """Refuse a conversion to float."""
        raise self._untraceable("float()")

    def __int__(self):
        """Refuse a conversion to int."""
        raise self._untraceable("int()")

    def __index__(self):
        """Refuse use as an index."""
        raise self._untraceable("an index")

    def __format__(self, spec):
        """Refuse string formatting of a value that has no number yet."""
        raise self._untraceable("string formatting")

    def __array__(self, *args, **kwargs):
        """Refuse a NumPy conversion."""
        raise self._untraceable("a NumPy conversion")

    def __repr__(self):
        """Return ``Proxy(%index)``."""
        return f"Proxy({self.node.label()})"

    def _untraceable(self, what):
        return TraceError(
            f"{self.graph.module_path}: {what} of traced value {self.node.label()} cannot be "
            f"traced (at {self.node.source or 'graph input'}); use gemini.ops.where, check or "
            "logical_and"
        )
