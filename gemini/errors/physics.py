"""Errors raised by unit conversion and physical correlations."""

from gemini.errors.base import GeminiError


class UnitError(GeminiError, ValueError):
    """A unit is unknown, or cannot be converted to the requested unit."""

    code = "invalid_unit"


class PhysicsRangeError(GeminiError, ValueError):
    """An input lies outside the domain where a correlation is defined."""

    code = "physics_range"


class SolverError(PhysicsRangeError):
    """An iterative solve did not converge inside its bracket or iteration limit."""

    code = "solver_failed"


class UnknownCorrelationError(GeminiError, ValueError):
    """A correlation, model or material name is not supported."""

    code = "unknown_name"


class MissingChemistryError(GeminiError, ValueError):
    """A correlation needs fluid chemistry that was not supplied."""

    code = "missing_value"


class InsufficientDataError(GeminiError, ValueError):
    """A fit or estimate has too few valid observations."""

    code = "invalid_data"
