"""Mass and energy close for every shipped plant and every module in it, on a run."""

import pytest

import gemini as gm
from tests.fixtures.balance import assert_plant_closes
from tests.fixtures.heating_cooling import configure, filled_spec, two_ticks

pytestmark = pytest.mark.e2e
TEMPLATES = (
    "heating_only",
    "heating_absorption_cooling",
    "heating_heat_pump_compression_cooling",
    "heating_full_cooling",
    "heating_cooling",
)


@pytest.mark.parametrize("name", TEMPLATES)
def test_a_heating_and_cooling_plant_closes(name):
    """The root's in and out are the ports of its grids, its air and its aquifers."""
    plant = configure(gm.plants.from_spec(filled_spec(name)))
    results = gm.simulate(plant, two_ticks(), on_error="raise")
    assert_plant_closes(plant, results)


@pytest.mark.parametrize("frequency", [55, 60, 65])
def test_the_doublet_heat_plant_closes(frequency):
    """A simulated day of the shipped example closes tick by tick."""
    plant = gm.plants.example("DoubletHeatPlant")
    clock = gm.Clock.days(2027, 1, 1, days=1)
    profiles = {
        "doublet.reservoir.production_rate": gm.Profile.constant(150, unit="m3/h", clock=clock),
        "doublet.esp.frequency": gm.Profile.constant(frequency, unit="Hz", clock=clock),
        "injection_pump.pressure_setpoint": gm.Profile.constant(51.5, unit="bar", clock=clock),
    }
    results = gm.simulate(plant, gm.Dataset.from_profiles(profiles), clock=clock)
    assert_plant_closes(plant, results)
