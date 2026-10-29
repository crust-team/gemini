"""Engine error classes keep their built-in bases."""

import pytest

import gemini as gm
from gemini.errors import engine
from gemini.errors.base import GeminiError

BASES = {
    "DatasetError": (TypeError, ValueError),
    "ClockError": (KeyError, ValueError),
    "BindingError": (ValueError,),
    "MissingMeasurementError": (ValueError,),
    "StepError": (ValueError,),
    "CheckpointError": (RuntimeError, ValueError),
    "PlantFormatError": (TypeError, ValueError),
    "UnknownResultError": (KeyError, AttributeError),
}


@pytest.mark.parametrize("name", sorted(BASES))
def test_class_derives_from_gemini_error_and_builtins(name):
    """Existing ``except`` clauses for the built-in classes keep catching the error."""
    cls = getattr(engine, name)
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
        for name, value in vars(engine).items()
        if isinstance(value, type) and issubclass(value, GeminiError) and value is not GeminiError
    }
    assert defined == set(BASES)
