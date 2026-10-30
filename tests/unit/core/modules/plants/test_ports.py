"""Port lookups and rules of ``Plant.connect``."""

import pytest

import gemini as gm
from gemini.core.modules.plants import ports
from gemini.errors import ValidationError


@pytest.fixture
def plant():
    """Return a plant with a filter and a pipe."""
    result = gm.Plant("Ports")
    result.add("Filter", "filter")
    result.add("Pipe", "pipe")
    return result


def test_ends_can_be_modules_declarations_or_text(plant):
    """Handles, port declarations and ``path.port`` name the same connection."""
    plant.connect(plant.filter.outlet, plant.pipe)
    assert plant._connection_list()[0]["source"] == "filter.outlet"
    assert plant._connection_list()[0]["target"] == "pipe.inlet"


def test_a_module_with_no_free_port_is_in_use(plant):
    """Matching a module whose only outlet is connected raises ``port_in_use``."""
    plant.connect("filter", "pipe")
    plant.add("Pipe", "other")
    with pytest.raises(ValidationError) as caught:
        plant.connect("filter", "other")
    assert caught.value.code == "port_in_use"


def test_a_port_name_that_is_taken_is_refused(plant):
    """Plant port names are unique and cannot be module names."""
    plant.connect("feed", "filter.inlet")
    with pytest.raises(ValidationError) as caught:
        plant.connect("feed", "pipe.inlet")
    assert caught.value.code == "invalid_connection"


def test_port_map_lists_named_then_free_ports(plant):
    """Named ports first, then every free port named from its path."""
    plant.connect("feed", "filter.inlet")
    assert plant._port_map("inlets") == {
        "feed": ("filter", "inlet"),
        "pipe_inlet": ("pipe", "inlet"),
    }
    assert list(plant._port_map("outlets")) == ["filter_outlet", "pipe_outlet"]


def test_bad_ends_raise_validation_errors(plant):
    """Something that is not an end is refused with its field."""
    with pytest.raises(ValidationError) as caught:
        plant.connect(3, "pipe.inlet")
    assert caught.value.path == "source"
    assert ports.PortResolver.__doc__
