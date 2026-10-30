"""One call of one module from plain JSON."""

from gemini.errors import NotImplementedYet


def evaluate(module, parameters, inlets, controls):
    """Return ``{outlets, outputs, errors}`` of one call of a registered module or class."""
    raise NotImplementedYet(f"evaluate: module = {module!r}")
