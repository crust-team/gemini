"""Module containers mirroring the useful parts of ``torch.nn`` containers."""

from collections.abc import Mapping, MutableMapping, MutableSequence

from gemini.core.modules.module import Module


class ModuleList(Module, MutableSequence):
    """List-like registration of child modules with numeric names."""

    def __init__(self, modules=()):
        """Register an iterable of modules under numeric names."""
        super().__init__()
        self.extend(modules)

    def _rebuild(self, modules):
        self._children.clear()
        for index, module in enumerate(modules):
            self.add_module(str(index), module)

    def __getitem__(self, index):
        """Return one child or a new container for a slice."""
        values = list(self._children.values())
        return ModuleList(values[index]) if isinstance(index, slice) else values[index]

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

    def insert(self, index, value):
        """Insert a child and renumber later children."""
        values = list(self._children.values())
        values.insert(index, value)
        self._rebuild(values)

    def __iter__(self):
        """Iterate children in registration order."""
        return iter(self._children.values())


class ModuleDict(Module, MutableMapping):
    """Mapping-like registration of child modules by caller-provided keys."""

    def __init__(self, modules=()):
        """Register modules from a mapping or iterable of pairs."""
        super().__init__()
        self.update(dict(modules))

    def __getitem__(self, key):
        """Return a child by key."""
        return self._children[key]

    def __setitem__(self, key, value):
        """Register or replace a child by key."""
        self.add_module(key, value)

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


class Sequential(Module):
    """Chain modules with exactly one fluid inlet and one fluid outlet each."""

    def __init__(self, *modules):
        """Register positional modules or modules from one mapping."""
        super().__init__()
        items = (
            modules[0].items()
            if len(modules) == 1 and isinstance(modules[0], Mapping)
            else enumerate(modules)
        )
        for name, module in items:
            self.add_module(str(name), module)
        if not self._children:
            raise ValueError("Sequential requires at least one child")

    def __call__(self, stream, controls=None):
        """Pass one stream through the children in registration order."""
        controls = controls or {}
        results = {}
        for name, child in self.named_children():
            if len(child.inlets()) != 1:
                raise ValueError("Sequential children require exactly one inlet")
            fluid_outlets = [
                key for key, value in child.outlets().items() if value.kind.__name__ == "Stream"
            ]
            if len(fluid_outlets) != 1:
                raise ValueError("Sequential children require exactly one fluid outlet")
            result = child(**({next(iter(child.inlets())): stream} | controls.get(name, {})))
            stream = result.outlets[fluid_outlets[0]]
            results[name] = result
        return stream
