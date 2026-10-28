"""Immutable named fluid ports passed through module calls."""

from collections.abc import Iterator, Mapping
from difflib import get_close_matches

from gemini.core.types.flows import Stream


class Ports(Mapping[str, Stream]):
    """Read-only, ordered mapping of port names to fluid streams."""

    __slots__ = ("_values", "_path")

    def __init__(self, values=None, *, path="module"):
        """Retain one private copy and the module path used in access errors."""
        copied = dict(values or {})
        valid = ", ".join(copied) or "<none>"
        for name, value in copied.items():
            if not isinstance(name, str):
                raise TypeError(f"{path}: port names must be strings; valid names: {valid}")
            if not isinstance(value, Stream):
                raise TypeError(f"{path}: port {name!r} must be a Stream; valid names: {valid}")
        object.__setattr__(self, "_values", copied)
        object.__setattr__(self, "_path", path)

    def _unknown(self, name):
        valid = list(self._values)
        suggestion = get_close_matches(str(name), valid, n=1)
        detail = f"; did you mean {suggestion[0]!r}?" if suggestion else ""
        return (
            f"{self._path}: unknown port {name!r}; "
            f"valid names: {', '.join(valid) or '<none>'}{detail}"
        )

    def __getitem__(self, name):
        """Return one stream, with an actionable error for an unknown port."""
        try:
            return self._values[name]
        except KeyError as exc:
            raise KeyError(self._unknown(name)) from exc

    def __getattr__(self, name):
        """Return one stream by attribute name."""
        try:
            values = object.__getattribute__(self, "_values")
        except AttributeError:
            raise AttributeError(name) from None
        try:
            return values[name]
        except KeyError as exc:
            raise AttributeError(self._unknown(name)) from exc

    def __iter__(self) -> Iterator[str]:
        """Iterate port names in declaration order."""
        return iter(self._values)

    def __len__(self):
        """Return the number of ports."""
        return len(self._values)

    def __setattr__(self, name, value):
        """Reject attribute assignment after construction."""
        del name, value
        raise AttributeError("Ports is immutable")

    def __delattr__(self, name):
        """Reject attribute deletion."""
        del name
        raise AttributeError("Ports is immutable")

    def __repr__(self):
        """Represent the contained streams as a plain mapping."""
        return repr(self._values)

    def __copy__(self):
        """Reuse this immutable mapping in shallow copies."""
        return self

    def __deepcopy__(self, memo):
        """Reuse this immutable mapping in deep copies."""
        del memo
        return self
