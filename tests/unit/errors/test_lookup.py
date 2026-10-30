"""The private classes that give ``ValidationError`` the built-in Python's protocols need."""

import copy
import pickle

import pytest

import gemini as gm
from gemini.errors import lookup


@pytest.mark.parametrize("cls", [lookup.UnknownKey, lookup.UnknownPort, lookup.UnknownMember])
def test_each_is_a_validation_error_and_is_not_public(cls):
    """A caller catches ``ValidationError``; the classes are not in ``gm.errors``."""
    assert issubclass(cls, gm.errors.ValidationError) and cls.__doc__
    assert issubclass(cls, ValueError) and issubclass(cls, AttributeError)
    assert cls.__name__ not in gm.errors.__all__ and not hasattr(gm.errors, cls.__name__)
    with pytest.raises(gm.errors.ValidationError):
        raise cls("message")


@pytest.mark.parametrize("cls", [lookup.UnknownKey, lookup.UnknownPort])
def test_a_keyed_class_serves_mappings_and_keeps_its_message_without_quotes(cls):
    """A plain ``KeyError`` prints quotes; these print the message itself."""
    assert issubclass(cls, KeyError)
    assert str(cls("no such key")) == "no such key"
    assert cls("no such key").to_dict()["message"] == "no such key"


def test_the_codes_say_what_is_unknown():
    """A port has its own code; the rest are unknown names."""
    assert lookup.UnknownKey.code == "unknown_name"
    assert lookup.UnknownPort.code == "unknown_port"
    assert lookup.UnknownMember.code == "unknown_name"


def _describe(name, subject):
    return f"{subject}: no {name}"


def test_a_member_builds_its_message_only_when_read():
    """``hasattr`` misses cost nothing; the message comes from the module-level function."""
    error = lookup.UnknownMember("flow", "esp", _describe)
    assert str(error) == "esp: no flow" and error.member == "flow"


def test_a_copied_or_pickled_member_keeps_the_finished_message():
    """The module is not kept, only the text."""
    error = lookup.UnknownMember("flow", "esp", _describe)
    assert str(pickle.loads(pickle.dumps(error))) == "esp: no flow"
    assert str(copy.copy(error)) == "esp: no flow"


def test_getattr_with_a_default_and_hasattr_work_on_a_module():
    """The protocol this file exists for."""
    module = gm.modules.ESP()
    assert not hasattr(module, "no_such_member")
    assert getattr(module, "no_such_member", 3) == 3
