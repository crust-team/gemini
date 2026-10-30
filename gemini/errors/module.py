"""Errors in defining, configuring and calling modules."""

from gemini.errors.base import GeminiError


class DeclarationError(GeminiError, TypeError, ValueError):
    """A module class or tree is defined wrongly: declarations, children, containers or hooks."""


class UnknownNameError(GeminiError, ValueError):
    """A module path, parameter, control, boundary or state name does not exist."""


class UnknownPortError(GeminiError, KeyError, AttributeError):
    """A port or recorded value name does not exist in a ``Ports`` or ``Values`` mapping."""


def _name_only(name, subject):
    """Describe an unknown member without any module context."""
    return str(name)


def _stored_text(name, subject):
    """Return a message that was already built, for a copied or unpickled error."""
    return subject


class UnknownMemberError(GeminiError, AttributeError):
    """A module has no child, declaration or port with the requested attribute name.

    Misses through ``hasattr`` and ``getattr`` with a default are frequent, so the error only
    keeps the missing name and the module. ``describe(name, subject)`` builds the message, with
    its close-match suggestion, when the error is printed. ``describe`` must be a module-level
    function. Copying or pickling the error stores the finished message instead of the module.
    """

    def __init__(self, name, subject=None, describe=_name_only):
        """Keep the missing name, the module and the function that describes the miss."""
        super().__init__(name)
        self.member = name
        self.subject = subject
        self.describe = describe

    def __str__(self):
        """Return the module path, the unknown name and the closest valid name."""
        return self.describe(self.member, self.subject)

    def __reduce__(self):
        """Rebuild the error from its finished message."""
        return type(self), (self.member, str(self), _stored_text)


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


class TraceError(GeminiError, TypeError):
    """A module cannot be traced into a computation graph, so it runs untraced (graph break)."""
