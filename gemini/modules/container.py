"""Ordered list and mapping containers for child modules."""

from collections.abc import MutableMapping, MutableSequence

from gemini.modules.module import Module


class ModuleList(Module, MutableSequence):
    """List-like registration of child modules under the names ``"0"``, ``"1"``, ...

    Removing or inserting a child renumbers the later children, so their paths change.
    """

    def __init__(self, modules=()):
        """Register an iterable of modules under numeric names."""
        super().__init__()
        self.extend(modules)

    def _rebuild(self, modules):
        for name in tuple(self._children):
            object.__delattr__(self, name)
        self._children.clear()
        for index, module in enumerate(modules):
            self._add_module(str(index), module)

    def __getitem__(self, index):
        """Return one child, or a plain list of children for a slice."""
        return list(self._children.values())[index]

    def __setitem__(self, index, value):
        """Replace a child by index."""
        values = list(self._children.values())
        values[index] = value
        self._rebuild(values)

    def __delitem__(self, index):
        """Remove a child by index and renumber later children."""
        values = list(self._children.values())
        del values[index]
        self._rebuild(values)

    def __len__(self):
        """Return the number of children."""
        return len(self._children)

    def __iter__(self):
        """Iterate children in registration order."""
        return iter(self._children.values())

    def insert(self, index, value):
        """Insert a child and renumber later children."""
        values = list(self._children.values())
        values.insert(index, value)
        self._rebuild(values)


class ModuleDict(Module, MutableMapping):
    """Mapping-like registration of child modules by caller-provided keys.

    Keys must not shadow module or mapping attributes such as ``step`` or ``keys``. Like every
    module, a container compares and hashes by identity, not by its contents.
    """

    __eq__ = object.__eq__
    __hash__ = object.__hash__
    get = MutableMapping.get

    def __init__(self, modules=()):
        """Register modules from a mapping or iterable of pairs."""
        super().__init__()
        self.update(dict(modules))

    def __getitem__(self, key):
        """Return a child by key."""
        return self._children[key]

    def __setitem__(self, key, value):
        """Register or replace a child by key."""
        self._add_module(key, value)

    def __delitem__(self, key):
        """Remove a registered child."""
        del self._children[key]
        object.__delattr__(self, key)

    def __iter__(self):
        """Iterate registered child names."""
        return iter(self._children)

    def __len__(self):
        """Return the number of children."""
        return len(self._children)
