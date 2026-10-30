"""What a module says about itself as plain JSON: ``describe``, its schema, its checks."""

from gemini.errors import NotImplementedYet


def describe(module):
    """Return the description dictionary of a module instance."""
    raise NotImplementedYet(f"{module.path}: describe")


def parameter_schema(module):
    """Return the JSON Schema of a module's parameters, each property with its ``unit``."""
    raise NotImplementedYet(f"{module.path}: parameter_schema")


def validate_params(module, params):
    """Return every problem of ``params`` as ``[{path, message, code}]``; never raises for them."""
    raise NotImplementedYet(f"{module.path}: validate_params")
