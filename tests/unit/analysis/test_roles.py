"""Roles come from the wiring, not from the class."""

import pytest

import gemini as gm
from gemini.analysis import roles
from gemini.errors import ValidationError
from tests.fixtures.errors import raises


def chiller_plant(*units):
    """Return chilled water through ``units`` of type and name to a cooling grid."""
    plant = gm.Plant("Chilled")
    plant.add("CoolingGrid", name="users")
    running = "users.return_out"
    for type_name, name, inlet, outlet in units:
        plant.add(type_name, name=name)
        plant.connect(running, f"{name}.{inlet}")
        running = f"{name}.{outlet}"
    plant.connect(running, "users.supply_in")
    return plant


COMPRESSION = ("HeatPump", "chiller", "source_in", "source_out")


def test_a_heat_pump_on_the_cooling_grid_is_the_compression_chiller():
    """Not the heating heat pump: it serves the cooling grid."""
    assert roles.heat_pumps(chiller_plant(COMPRESSION)) == (None, "chiller")
    assert roles.cooling_units(chiller_plant(COMPRESSION)) == {"compression": "chiller"}


def test_a_heat_pump_and_a_compression_chiller_are_two_roles():
    """The plant that a single ``HeatPump`` rule refused."""
    plant = gm.plants.get("HeatingCoolingPlant")
    assert roles.heat_pumps(plant) == ("heat_pump", "compression_chiller")


def test_every_cooling_unit_of_a_plant_has_its_kind():
    """In the order of the kinds, heat-driven first."""
    assert roles.cooling_units(gm.plants.get("HeatingCoolingPlant")) == {
        "absorption": "absorption_chiller",
        "adsorption": "adsorption_chiller",
        "compression": "compression_chiller",
    }


def test_two_units_of_one_role_and_kind_break_the_design():
    """The message names both."""
    second = ("HeatPump", "other", "source_in", "source_out")
    with raises(ValidationError, "invalid_design", match="chiller, other"):
        roles.cooling_units(chiller_plant(COMPRESSION, second))


def test_a_heat_pump_that_serves_both_grids_is_refused():
    """One setpoint cannot hold two supplies."""
    plant = gm.Plant("Both")
    for name, type_name in (("cold", "CoolingGrid"), ("hot", "HeatingGrid"), ("pump", "HeatPump")):
        plant.add(type_name, name=name)
    plant.connect("cold.return_out", "pump.source_in")
    plant.connect("pump.source_out", "cold.supply_in")
    plant.connect("hot.return_out", "pump.sink_in")
    plant.connect("pump.sink_out", "hot.supply_in")
    with raises(ValidationError, "invalid_design", match="both grids"):
        roles.heat_pumps(plant)


@pytest.mark.parametrize("kind", ["AbsorptionUnit", "AdsorptionChiller"])
def test_a_chiller_off_the_cooling_grid_has_no_role(kind):
    """Its chilled water serves nothing the schedule knows."""
    plant = gm.Plant("Loose")
    plant.add(kind, name="unit")
    assert roles.cooling_units(plant) == {}
