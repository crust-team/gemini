"""Plants built from data: a ``Module`` whose forward runs its children in connection order."""

from gemini.core.modules.module import Module


class Plant(Module):
    """A plant built from named modules and connections, a normal composite ``Module``."""

    category = "plant"

    def __init__(self, name):
        """Start an empty plant called ``name``."""
        super().__init__()
        self._name = name
