"""Roots of every GEMINI exception and warning."""


class GeminiError(Exception):
    """Base class of every error GEMINI raises on purpose; catch it to handle them all."""


class GeminiWarning(UserWarning):
    """Base class of every warning GEMINI emits."""
