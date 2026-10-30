"""Errors in defining, configuring and calling modules."""

from gemini.errors.base import GeminiError


class DeclarationError(GeminiError, TypeError, ValueError):
    """A module class or tree is defined wrongly: declarations, children, containers or hooks."""


class UnknownNameError(GeminiError, ValueError):
    """A module path, parameter, control, boundary or state name does not exist."""


class UnknownPortError(GeminiError, KeyError, AttributeError):
    """A port or recorded value name does not exist in a ``Ports`` or ``Values`` mapping."""


class CallError(GeminiError, TypeError):
    """A module was called with wrong, missing, duplicate or invalid inlet or input arguments."""


class OutletError(GeminiError, TypeError, ValueError):
    """``forward`` returned something other than a dictionary of the declared outlets."""


class MissingValueError(GeminiError, RuntimeError, TypeError):
    """A parameter, control or boundary has no value and no default."""


class OutputError(GeminiError, RuntimeError):
    """An output was assigned outside output computation, or left unassigned."""


class FormulaError(GeminiError, TypeError, ValueError):
    """An ``Output.of``, ``Output.ratio`` or automatic-sum formula cannot be resolved."""


class ConfigurationError(GeminiError, ValueError):
    """Equipment design data needed for this call is missing or inconsistent."""
