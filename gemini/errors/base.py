"""Roots of every GEMINI exception and warning, and the fixed lists of error codes."""

CODES = (
    "error",
    "invalid_value",
    "out_of_bounds",
    "missing_value",
    "invalid_unit",
    "unknown_name",
    "unknown_port",
    "invalid_call",
    "invalid_format",
    "old_format",
    "migration_failed",
    "invalid_connection",
    "stream_mismatch",
    "ambiguous_port",
    "port_in_use",
    "loop_without_state",
    "invalid_binding",
    "missing_column",
    "invalid_data",
    "physics_range",
    "solver_failed",
    "cancelled",
    "not_implemented",
)
"""Every value of ``GeminiError.code``; the backend puts them into ``422`` details."""

ROW_CODES = {
    "missing_value": "A bound column has no finite value at this tick; the row was skipped.",
    "invalid_inlet": "An inlet stream breaks the stream limits; the row failed.",
    "out_of_bounds": "A control, boundary or output is outside its bounds; the row failed.",
    "physics_range": "An input is outside the domain of a correlation; the row failed.",
    "solver_failed": "An iterative solve did not converge; the row failed.",
    "module_error": "A module raised any other error; the row failed.",
}
"""Every row code of ``Results.errors()`` with its meaning."""


def problem(path, code, message, suggestions=(), time=None):
    """Return the shape ``{path, code, message, suggestions}`` of every problem as plain JSON.

    A failed run row adds ``time``. The one helper of the shape, here because ``gemini.errors`` is
    a leaf package and ``to_dict`` returns one; ``gemini.types.shapes`` exports it with the others.
    """
    shape = {"path": path, "code": code, "message": str(message), "suggestions": list(suggestions)}
    return shape if time is None else shape | {"time": time}


class GeminiError(Exception):
    """Base class of every error GEMINI raises on purpose; catch it to handle them all.

    ``path`` says where the problem is (a dotted module path or a path into a spec),
    ``suggestions`` lists close valid names and ``code`` is one of ``CODES``, by default the
    class attribute. ``to_dict`` gives the JSON form used in ``422`` details and tool results.
    """

    code = "error"
    path = None
    suggestions = ()

    def __init__(self, *args, path=None, code=None, suggestions=()):
        """Keep the message and the optional location, code and close-match names."""
        super().__init__(*args)
        if code is not None:
            if code not in CODES:
                raise GeminiError(f"GeminiError: code = {code!r}; expected one of CODES")
            self.code = code
        if path is not None:
            self.path = path
        if suggestions:
            self.suggestions = tuple(suggestions)

    def to_dict(self):
        """Return the problem ``{path, code, message, suggestions}`` as plain JSON."""
        message = self.args[0] if isinstance(self, KeyError) and self.args else self
        return problem(self.path, self.code, message, self.suggestions)


class GeminiWarning(UserWarning):
    """Base class of every warning GEMINI emits."""


class ValidationError(GeminiError, ValueError):
    """A value, a spec or a run input breaks a documented rule; every problem is in the message."""

    code = "invalid_value"


class Cancelled(GeminiError):
    """A callback stopped a run; the ticks already committed stay readable."""

    code = "cancelled"


class NotImplementedYet(GeminiError, NotImplementedError):
    """The name is final but its work lands in a later step."""

    code = "not_implemented"
