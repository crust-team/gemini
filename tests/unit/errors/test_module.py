"""Module error classes keep their built-in bases."""

import pytest

import gemini as gm
from gemini.errors import module
from gemini.errors.base import GeminiError

BASES = {
    "DeclarationError": (TypeError, ValueError),
    "UnknownNameError": (ValueError,),
    "UnknownPortError": (KeyError, AttributeError),
    "UnknownMemberError": (AttributeError,),
    "CallError": (TypeError,),
    "OutletError": (TypeError, ValueError),
    "MissingValueError": (RuntimeError, TypeError),
    "OutputError": (RuntimeError,),
    "FormulaError": (TypeError, ValueError),
    "ConfigurationError": (ValueError,),
    "TraceError": (TypeError,),
}


@pytest.mark.parametrize("name", sorted(BASES))
def test_class_derives_from_gemini_error_and_builtins(name):
    """Existing ``except`` clauses for the built-in classes keep catching the error."""
    cls = getattr(module, name)
    assert getattr(gm.errors, name) is cls
    assert issubclass(cls, GeminiError)
    for builtin in BASES[name]:
        assert issubclass(cls, builtin)
    with pytest.raises(BASES[name][0]):
        raise cls("message")


def test_file_lists_exactly_these_classes():
    """Every class in this file is covered above."""
    defined = {
        name
        for name, value in vars(module).items()
        if isinstance(value, type) and issubclass(value, GeminiError) and value is not GeminiError
    }
    assert defined == set(BASES)
