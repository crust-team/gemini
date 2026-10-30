"""``ValidationError`` for Python's protocols; private, never in ``gm.errors``.

``hasattr``, ``getattr`` with a default and mapping lookups need ``AttributeError`` or ``KeyError``,
so an unknown name in those places raises one of these. Callers catch ``ValidationError`` or the
built-in and read ``code``.
"""

from gemini.errors.base import ValidationError


class UnknownKey(ValidationError, KeyError, AttributeError):
    """A name does not exist in a mapping or an attribute view of one."""

    code = "unknown_name"

    __str__ = Exception.__str__


class UnknownPort(UnknownKey):
    """A port or recorded value name does not exist in a ``Ports`` or ``Values`` mapping."""

    code = "unknown_port"


def _name_only(name, subject):
    """Describe an unknown member without any module context."""
    return str(name)


def _stored_text(name, subject):
    """Return a message that was already built, for a copied or unpickled error."""
    return subject


class UnknownMember(ValidationError, AttributeError):
    """A module has no child, declaration or port with the requested attribute name.

    Misses through ``hasattr`` and ``getattr`` with a default are frequent, so the error only
    keeps the missing name and the module. ``describe(name, subject)`` builds the message, with
    its close-match suggestion, when the error is printed. ``describe`` must be a module-level
    function. Copying or pickling the error stores the finished message instead of the module.
    """

    code = "unknown_name"

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
