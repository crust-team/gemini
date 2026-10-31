"""Port lookups and rules of ``Plant.connect``."""

import pytest

import gemini as gm
from gemini.errors import ValidationError
from gemini.plants._utils import ports


@pytest.fixture
def plant():
    """Return a plant with a filter and a pipe."""
    result = gm.Plant("Ports")
    result.add("Filter", "filter")
    result.add("Pipe", "pipe")
    return result


def test_ends_can_be_modules_declarations_or_text(plant):
    """Handles, port declarations and ``path.port`` name the same connection."""
    plant.connect(plant.filter.fluid_out, plant.pipe)
    assert plant._connection_list()[0]["source"] == "filter.fluid_out"
    assert plant._connection_list()[0]["target"] == "pipe.fluid_in"


def test_a_module_with_no_free_port_is_in_use(plant):
    """Matching a module whose only outlet is connected raises ``port_in_use``."""
    plant.connect("filter", "pipe")
    plant.add("Pipe", "other")
    with pytest.raises(ValidationError) as caught:
        plant.connect("filter", "other")
    assert caught.value.code == "port_in_use"


def test_a_port_name_that_is_taken_is_refused(plant):
    """Plant port names are unique and cannot be module names."""
    plant.connect("feed", "filter.fluid_in")
    with pytest.raises(ValidationError) as caught:
        plant.connect("feed", "pipe.fluid_in")
    assert caught.value.code == "invalid_connection"


def test_port_map_lists_only_named_ports(plant):
    """A free port of a child is not a plant port; it is an unconnected port."""
    plant.connect("feed", "filter.fluid_in")
    assert plant._port_map("inlets") == {"feed": ("filter", "fluid_in")}
    assert plant._port_map("outlets") == {}
    assert plant._unconnected_ports() == [
        ("outlets", "filter", "fluid_out"),
        ("outlets", "pipe", "fluid_out"),
        ("outlets", "pipe", "loss_out"),
        ("inlets", "pipe", "fluid_in"),
        ("inlets", "pipe", "air_in"),
    ]


def test_bad_ends_raise_validation_errors(plant):
    """Something that is not an end is refused with its field."""
    with pytest.raises(ValidationError) as caught:
        plant.connect(3, "pipe.fluid_in")
    assert caught.value.path == "source"
    assert ports.PortResolver.__doc__
