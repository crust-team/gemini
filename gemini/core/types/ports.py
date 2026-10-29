"""Immutable named fluid ports passed through module calls."""

from gemini.core.types.flows import Stream
from gemini.errors import CallError
from gemini.utils.mappings import AttributeMapping
from gemini.utils.strings import did_you_mean, join_names


class Ports(AttributeMapping):
    """Read-only, ordered mapping of port names to fluid streams."""

    def __init__(self, values=None, *, path="module"):
        """Retain one private copy and the module path used in access errors."""
        super().__init__(values)
        valid = join_names(self._values)
        for name, value in self._values.items():
            if not isinstance(name, str):
                raise CallError(
                    f"{path}: port name = {name!r}; expected a string; valid names: {valid}"
                )
            if not isinstance(value, Stream):
                raise CallError(
                    f"{path}: port {name!r} = {value!r}; expected a Stream; valid names: {valid}"
                )
        object.__setattr__(self, "_path", path)

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
