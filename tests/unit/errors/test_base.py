"""Roots of the GEMINI error and warning hierarchy."""

import gemini as gm
from gemini.errors import base


def test_roots_derive_from_the_builtin_roots():
    """Catching ``GeminiError`` or ``GeminiWarning`` catches everything GEMINI raises or warns."""
    assert issubclass(base.GeminiError, Exception)
    assert issubclass(base.GeminiWarning, UserWarning)
    assert gm.errors.GeminiError is base.GeminiError


def test_every_exported_class_has_a_gemini_root():
    """Every public class derives from a GEMINI root and is documented."""
    for name in gm.errors.__all__:
        cls = getattr(gm.errors, name)
        assert issubclass(cls, (base.GeminiError, base.GeminiWarning)), name
        assert cls.__doc__, name
