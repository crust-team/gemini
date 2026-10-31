"""``BoilerChpPlant``: the upstream ``doublet_plant`` example with a boiler and a CHP."""

import pytest

import gemini as gm

SECONDARY = gm.Stream(flow="140 m3/h", T="20 degC", p="3 bar", fluid=gm.Fluid(kind="water"))
INPUTS = {
    "doublet.esp.frequency": "65 Hz",
    "doublet.wellhead_pressure": "3 bar",
    "splitter.split_fraction": 0.5,
    "boiler.temperature_setpoint": "70 degC",
    "chp.load_fraction": 1.0,
    "air.temperature": "10 degC",
}


@pytest.fixture(scope="module")
def run():
    """Return the example plant and one call of it."""
    plant = gm.plants.example("BoilerChpPlant")
    plant.set_inputs(INPUTS)
    return plant, plant(return_in=SECONDARY)


def test_the_call_reproduces_the_case(run):
    """The solved rate, the duty, the mixed outlet and the energy flows of the case."""
    _, result = run
    outputs, flows = result.outputs, gm.modules.collect_flows(result)
    assert round(outputs.production_rate * 3.6, 2) == 129.02
    assert round(outputs.get("duty", unit="MW"), 3) == 3.961
    assert round(outputs.get("supply_out_T", unit="degC"), 2) == 47.74
    assert round(flows["fuel"] / 1e6, 3) == 1.174
    assert round(flows["electricity_generated"] / 1e6, 3) == 0.400


def test_the_injector_needs_no_pump(run):
    """The 3100 m column over-delivers, so the injection pump draws nothing."""
    assert run[1].outputs.injection_pump_power == 0


def test_the_call_closes(run):
    """Every balance of the plant closes."""
    plant, result = run
    assert all(check["passed"] for check in gm.checks.plant_balance(plant, result))
