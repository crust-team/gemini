"""Immutable named fluid ports passed through module calls."""

from gemini.errors import CallError, UnknownPortError
from gemini.types.flows import Stream
from gemini.utils.mappings import AttributeMapping
from gemini.utils.strings import did_you_mean, join_names


class Ports(AttributeMapping):
    """Read-only, ordered mapping of port names to fluid streams.

    Values are ``Stream`` objects, whose fields may be floats, arrays or traced values.
    """

    key_error = UnknownPortError
    attribute_error = UnknownPortError

    def __init__(self, values=None, *, path="module"):
        """Retain one private copy and the module path used in access errors."""
        super().__init__(values)
        for name, value in self._values.items():
            if not isinstance(name, str):
                raise CallError(
                    f"{path}: port name = {name!r}; expected a string; "
                    f"valid names: {join_names(self._values)}"
                )
            if not isinstance(value, Stream):
                raise CallError(
                    f"{path}: port {name!r} = {value!r}; expected a Stream; "
                    f"valid names: {join_names(self._values)}"
                )
        object.__setattr__(self, "_path", path)

    @classmethod
    def _trusted(cls, values, path):
        """Return ports over ``values``, a dict of streams this call owns, without checking them."""
        ports = object.__new__(cls)
        object.__setattr__(ports, "_values", values)
        object.__setattr__(ports, "_path", path)
        return ports

    def _unknown(self, name):
        """Name the module, the valid ports and the closest match."""
        return (
            f"{self._path}: unknown port {name!r}; "
            f"valid names: {join_names(self._values)}{did_you_mean(name, self._values)}"
        )

    def __setattr__(self, _name, _value):
        """Reject attribute assignment after construction."""
        raise AttributeError("Ports is immutable")

    def __delattr__(self, _name):
        """Reject attribute deletion."""
        raise AttributeError("Ports is immutable")

    def __copy__(self):
        """Reuse this immutable mapping in shallow copies."""
        return self

    def __deepcopy__(self, _memo):
        """Reuse this immutable mapping in deep copies."""
        return self
