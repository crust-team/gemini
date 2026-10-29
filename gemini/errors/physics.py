"""Errors raised by unit conversion and physical correlations."""

from gemini.errors.base import GeminiError


class UnitError(GeminiError, ValueError):
    """A unit is unknown, or cannot be converted to the requested unit."""


class PhysicsRangeError(GeminiError, ValueError):
    """An input lies outside the domain where a correlation is defined."""


class UnknownCorrelationError(GeminiError, ValueError):
    """A correlation, model or material name is not supported."""


class MissingChemistryError(GeminiError, ValueError):
    """A correlation needs fluid chemistry that was not supplied."""


class InsufficientDataError(GeminiError, ValueError):
    """A fit or estimate has too few valid observations."""
