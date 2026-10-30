"""Read-only mappings with attribute access, and lookups in nested dictionaries."""

from collections.abc import Iterator, Mapping


class AttributeMapping(Mapping):
    """Ordered read-only mapping whose keys are also readable as attributes.

    Subclasses describe unknown keys through ``_unknown(name)``. The message is raised as
    ``key_error`` for item access and ``attribute_error`` for attribute access; subclasses may
    replace both with one class deriving from ``KeyError`` and ``AttributeError``.
    """

    key_error = KeyError
    attribute_error = AttributeError

    def __init__(self, values=None):
        """Keep a private copy of ``values``."""
        object.__setattr__(self, "_values", dict(values or {}))

    def _unknown(self, name):
        """Describe an unknown key in an error message."""
        return name

    def __getitem__(self, name):
        """Return one value."""
        try:
            return self._values[name]
        except KeyError as exc:
            raise self.key_error(self._unknown(name)) from exc

    def __getattr__(self, name):
        """Return one value by attribute name."""
        try:
            values = object.__getattribute__(self, "_values")
        except AttributeError:
            raise AttributeError(name) from None
        try:
            return values[name]
        except KeyError as exc:
            raise self.attribute_error(self._unknown(name)) from exc

    def __contains__(self, name):
        """Return whether ``name`` is a key, without building an unknown-key message."""
        return name in self._values

    def __iter__(self) -> Iterator[str]:
        """Iterate keys in insertion order."""
        return iter(self._values)

    def __len__(self):
        """Return the number of keys."""
        return len(self._values)

    def __repr__(self):
        """Represent the contents as a plain dict."""
        return repr(self._values)


def get_nested(mapping, keys, default=None):
    """Return ``mapping[k1][k2]...``, or ``default`` when any level is missing."""
    value = mapping
    for key in keys:
        if key not in value:
            return default
        value = value[key]
    return value


def set_nested(mapping, keys, value):
    """Set ``mapping[k1][k2][...] = value``, creating missing intermediate dicts."""
    *parents, last = keys
    for key in parents:
        mapping = mapping.setdefault(key, {})
    mapping[last] = value
