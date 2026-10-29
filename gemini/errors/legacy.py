"""Errors in reading, converting and writing old-format GEMINI projects."""

from gemini.errors.base import GeminiError


class LegacyFormatError(GeminiError, ValueError):
    """An old project file is missing, malformed or describes an unsupported plant."""
