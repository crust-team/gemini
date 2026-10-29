"""Immutable named fluid ports passed through module calls."""

from gemini.core.types.flows import Stream
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
                raise TypeError(f"{path}: port names must be strings; valid names: {valid}")
            if not isinstance(value, Stream):
                raise TypeError(f"{path}: port {name!r} must be a Stream; valid names: {valid}")
        object.__setattr__(self, "_path", path)

    def _unknown(self, name):
        """Name the module, the valid ports and the closest match."""
        return (
            f"{self._path}: unknown port {name!r}; "
            f"valid names: {join_names(self._values)}{did_you_mean(name, self._values)}"
        )

    def __setattr__(self, name, value):
        """Reject attribute assignment after construction."""
        del name, value
        raise AttributeError("Ports is immutable")

    def __delattr__(self, name):
        """Reject attribute deletion."""
        del name
        raise AttributeError("Ports is immutable")

    def __copy__(self):
        """Reuse this immutable mapping in shallow copies."""
        return self

    def __deepcopy__(self, memo):
        """Reuse this immutable mapping in deep copies."""
        del memo
        return self
