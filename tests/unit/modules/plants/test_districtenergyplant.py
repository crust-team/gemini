"""``DistrictEnergyPlant``: a heating network and an ATES-cooled cooling network."""

import pytest

import gemini as gm

COOLING = "cooling.substations.0"
INPUTS = {
    "heating.pump.frequency": "50 Hz",
    "heating.splitters.0.split_fraction": 0.5,
    "heating.substations.0.valve.opening": 0.9,
    "heating.substations.1.valve.opening": 0.9,
    "heating.substations.0.consumer.heat_demand": "150 kW",
    "heating.substations.1.consumer.heat_demand": "100 kW",
    "cooling.pump.frequency": "50 Hz",
    f"{COOLING}.valve.opening": 0.9,
    f"{COOLING}.consumer.sensible_cooling_demand": "150 kW",
    f"{COOLING}.consumer.latent_cooling_demand": "0 kW",
    f"{COOLING}.consumer.indoor_temperature": "24 degC",
    f"{COOLING}.consumer.indoor_relative_humidity": 0.5,
    "ates.storage.groundwater_flow": "36 t/h",
    "ates.storage.mode": "charge",
    "ates.source_valve.split_fraction": 0.0,
    "ates.load_valve.split_fraction": 0.0,
    "ates.pump.frequency": "50 Hz",
    "ates.heat_pump.temperature_setpoint": "40 degC",
    "air.temperature": "10 degC",
}


@pytest.fixture(scope="module")
def run():
    """Return the example plant and two hourly steps, the return fed back."""
    plant = gm.plants.example("DistrictEnergyPlant")
    plant.set_inputs(INPUTS)
    inlets = {
        "hot_in": gm.Stream(flow="18 t/h", T="75 degC", p="6 bar"),
        "cold_in": gm.Stream(flow="36 t/h", T="17 degC", p="3 bar"),
        "air_in": gm.modules.Atmosphere.ambient_air("10 degC"),
    }
    state, first = plant.step(None, 3600, inlets)
    state, second = plant.step(state, 3600, inlets | {"cold_in": first.outlets.cold_out})
    return plant, first, second


def test_the_store_charges_step_by_step(run):
    """The stored energy starts at zero and grows with the warmed groundwater."""
    _, first, second = run
    assert first.children["ates"].children["storage"].outputs.stored_energy == 0
    assert (
        round(second.children["ates"].children["storage"].outputs.stored_energy / 3.6e9, 3) == 0.228
    )


def test_the_chilled_water_follows_the_returned_water(run):
    """The first step uses the given return, the second what the network gave back."""
    _, first, second = run
    assert round(first.children["ates"].outlets.supply_out.T - 273.15, 2) == 11.59
    assert round(second.children["ates"].outlets.supply_out.T - 273.15, 2) == 11.41


def test_every_step_closes(run):
    """Every balance of the plant closes on each step."""
    plant, first, second = run
    for result in (first, second):
        assert all(check["passed"] for check in gm.checks.plant_balance(plant, result))
