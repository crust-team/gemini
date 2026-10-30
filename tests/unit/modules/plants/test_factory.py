"""Registry types and groups become modules."""

import pytest

import gemini as gm
from gemini.errors import UnknownNameError
from gemini.modules.container import ModuleDict
from gemini.modules.plants.factory import make_module


def test_a_registry_name_a_class_and_a_group_make_modules():
    """Names and classes resolve to the registered type."""
    module, name = make_module("Filter")
    assert type(module) is gm.modules.Filter and name == "Filter"
    assert type(make_module(gm.modules.Filter)[0]) is gm.modules.Filter
    group, name = make_module("ModuleDict")
    assert isinstance(group, ModuleDict) and name == "ModuleDict"


def test_a_spec_plant_makes_a_new_plant_each_time():
    """A registered plant name builds a plant, never a shared one."""
    first, second = make_module("Doublet")[0], make_module("Doublet")[0]
    assert first is not second and first.name == "Doublet"


def test_unknown_types_point_at_the_type_with_a_suggestion():
    """The problem path is ``type`` and the closest name is suggested."""
    with pytest.raises(UnknownNameError) as caught:
        make_module("Degaser")
    assert caught.value.path == "type" and caught.value.suggestions[0] == "Degasser"


def test_an_unregistered_class_is_refused():
    """A class must be registered so the spec can name it."""

    class Mine(gm.modules.Module):
        category = "pumps"

    with pytest.raises(UnknownNameError):
        make_module(Mine)
