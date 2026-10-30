"""Roots of the GEMINI error and warning hierarchy."""

import json
import pickle

import pytest

import gemini as gm
from gemini import errors
from gemini.errors import base


def test_roots_derive_from_the_builtin_roots():
    """Catching ``GeminiError`` or ``GeminiWarning`` catches everything GEMINI raises or warns."""
    assert issubclass(base.GeminiError, Exception)
    assert issubclass(base.GeminiWarning, UserWarning)
    assert gm.errors.GeminiError is base.GeminiError


def test_every_exported_class_has_a_gemini_root():
    """Every public class derives from a GEMINI root and is documented."""
    for name in set(gm.errors.__all__) - {"CODES", "ROW_CODES"}:
        cls = getattr(gm.errors, name)
        assert issubclass(cls, (base.GeminiError, base.GeminiWarning)), name
        assert cls.__doc__, name


def test_to_dict_gives_the_fixed_shape():
    """``to_dict`` is the problem: plain JSON with the path, code, message and suggestions."""
    error = errors.UnknownNameError("no such name", path="doublet.esp", suggestions=("esp",))
    assert error.to_dict() == {
        "path": "doublet.esp",
        "code": "unknown_name",
        "message": "no such name",
        "suggestions": ["esp"],
    }
    assert json.dumps(error.to_dict())


def test_every_class_has_a_listed_code():
    """Each exported error class carries a code from the fixed list."""
    classes = [getattr(errors, name) for name in errors.__all__]
    for cls in classes:
        if isinstance(cls, type) and issubclass(cls, errors.GeminiError):
            assert cls.code in errors.CODES


def test_an_unlisted_code_is_refused():
    """A code outside ``CODES`` is a programming error."""
    with pytest.raises(errors.GeminiError, match="expected one of CODES"):
        errors.ValidationError("message", code="made_up")


def test_a_keyed_error_keeps_its_message_without_quotes():
    """A ``KeyError`` subclass prints quotes; ``to_dict`` gives the message itself."""
    assert errors.UnknownPortError("no port").to_dict()["message"] == "no port"


def test_pickling_keeps_location_and_suggestions():
    """A worker process can hand an error back with its details."""
    error = errors.UnitError("bad", path="a.b", code="invalid_unit", suggestions=("bar",))
    assert pickle.loads(pickle.dumps(error)).to_dict() == error.to_dict()


def test_new_classes_keep_the_builtin_families():
    """The new classes fit existing ``except`` clauses."""
    assert issubclass(errors.ValidationError, ValueError)
    assert issubclass(errors.DeclarationError, errors.ValidationError)
    assert issubclass(errors.BindingError, errors.ValidationError)
    assert issubclass(errors.SolverError, errors.PhysicsRangeError)
    assert issubclass(errors.NotImplementedYet, NotImplementedError)
    assert errors.ROW_CODES["missing_value"]
