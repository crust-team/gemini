"""Op dispatch: record an op on traced values, otherwise evaluate it on a backend.

``dispatch(name, *operands)`` is the single entry of every op. When an operand is
``Symbolic`` (a traced value of ``gemini.graph``), the op is recorded in that value's graph.
Otherwise every ``Constant`` operand is replaced by its plain Python value and the op runs on
the backend that ``gemini.backends.select`` chooses. ``Operators`` gives a class the Python
operators through the same entry.
"""

from gemini import backends
from gemini.ops import registry


class Symbolic:
    """Base of traced values: an op with a ``Symbolic`` operand is recorded, not evaluated."""

    def record(self, definition, operands, attributes=None):
        """Record ``definition`` applied to ``operands`` and return the traced result."""
        raise NotImplementedError(f"{type(self).__name__} does not record ops")


def dispatch(name, *operands, attributes=None):
    """Apply the op ``name`` to ``operands``: record it on traced values, else evaluate it."""
    definition = registry.get(name)
    for operand in operands:
        if isinstance(operand, Symbolic):
            return operand.record(definition, operands, attributes)
    values = tuple(
        operand.value if isinstance(operand, Constant) else operand for operand in operands
    )
    return backends.implementation(backends.select(values), name)(*values)


class Operators:
    """Python arithmetic and comparison operators that dispatch to the ops."""

    __array_ufunc__ = None

    def __add__(self, other):
        """Return ``self + other``."""
        return dispatch("add", self, other)

    def __radd__(self, other):
        """Return ``other + self``."""
        return dispatch("add", other, self)

    def __sub__(self, other):
        """Return ``self - other``."""
        return dispatch("sub", self, other)

    def __rsub__(self, other):
        """Return ``other - self``."""
        return dispatch("sub", other, self)

    def __mul__(self, other):
        """Return ``self * other``."""
        return dispatch("mul", self, other)

    def __rmul__(self, other):
        """Return ``other * self``."""
        return dispatch("mul", other, self)

    def __truediv__(self, other):
        """Return ``self / other``."""
        return dispatch("truediv", self, other)

    def __rtruediv__(self, other):
        """Return ``other / self``."""
        return dispatch("truediv", other, self)

    def __pow__(self, other):
        """Return ``self ** other``."""
        return dispatch("pow", self, other)

    def __rpow__(self, other):
        """Return ``other ** self``."""
        return dispatch("pow", other, self)

    def __mod__(self, other):
        """Return ``self % other``."""
        return dispatch("mod", self, other)

    def __rmod__(self, other):
        """Return ``other % self``."""
        return dispatch("mod", other, self)

    def __floordiv__(self, other):
        """Return ``self // other``."""
        return dispatch("floordiv", self, other)

    def __rfloordiv__(self, other):
        """Return ``other // self``."""
        return dispatch("floordiv", other, self)

    def __neg__(self):
        """Return ``-self``."""
        return dispatch("neg", self)

    def __abs__(self):
        """Return ``abs(self)``."""
        return dispatch("abs", self)

    def __lt__(self, other):
        """Return ``self < other``."""
        return dispatch("lt", self, other)

    def __le__(self, other):
        """Return ``self <= other``."""
        return dispatch("le", self, other)

    def __gt__(self, other):
        """Return ``self > other``."""
        return dispatch("gt", self, other)

    def __ge__(self, other):
        """Return ``self >= other``."""
        return dispatch("ge", self, other)


class Constant(Operators):
    """A named physical or model constant: fixed by default, a named graph input when traced.

    On concrete values a constant acts exactly like its Python float, including NumPy's
    weak-scalar promotion, so ``np.float32(x) / constant`` stays float32. A traced op records
    it as one graph input named ``name`` instead of a literal, so a sensitivity study can
    release it without retracing.
    """

    __slots__ = ("name", "value", "unit", "description")

    def __init__(self, name, value, unit, description):
        """Declare a constant with its SI ``value`` and ``unit``."""
        self.name = name
        self.value = float(value)
        self.unit = unit
        self.description = description

    def __float__(self):
        """Return the value."""
        return self.value

    def __format__(self, spec):
        """Format the value."""
        return format(self.value, spec)

    def __repr__(self):
        """Return ``Constant(name=value unit)``."""
        return f"Constant({self.name}={self.value!r} {self.unit})"
