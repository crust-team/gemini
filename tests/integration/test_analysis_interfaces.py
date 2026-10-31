"""Every analysis, economics, check, testing and optimisation name: JSON or not built."""

import copy
import json

import pytest

import gemini as gm
from tests.fixtures.booster_module import EXAMPLE, Booster
from tests.fixtures.costed_plants import day, heating_plant

CASE = {"wellhead_pressure": "4.6 bar", "rates": [20, 45], "frequency": 55.484}
CORROSION = {
    "correlation": "NORSOK",
    "conditions": {
        "temperature": "60 degC",
        "pressure": "20 bar",
        "water_flow_rate": 0.01,
        "co2_partial_pressure": "2 bar",
        "diameter": 0.1,
    },
    "thickness": 0.008,
    "minimum_thickness": 0.005,
    "start": "2024-01-01T00:00:00Z",
}
VALUES = gm.Assumptions(electricity_price=2e-8, heat_price=5e-8, electricity_emission_factor=1e-7)


@pytest.fixture(scope="module")
def example_run(shared_plant, fast_dataset):
    """Return a copy of the example plant and a six-hour replay of it."""
    plant = copy.deepcopy(shared_plant)
    return plant, gm.replay(plant, fast_dataset.window(None, "2024-07-01T06:00:00Z"))


def real_calls(example_run):
    """Return ``(name, result)`` of one call of every function that is built."""
    plant, replay = example_run
    costed, run = heating_plant(), day()
    return [
        ("analysis.nodal", gm.analysis.nodal(plant, "doublet", CASE)),
        ("analysis.pump_curve", gm.analysis.pump_curve(plant, "doublet.esp")),
        ("analysis.corrosion_forecast", gm.analysis.corrosion_forecast(CORROSION, "2026-01-01")),
        ("kpi", gm.evaluate.totals(plant, replay)),
        ("economics.capex", gm.evaluate.capex(costed)),
        ("economics.opex", gm.evaluate.opex(costed, run, VALUES)),
        ("economics.lcoh", gm.evaluate.lcoh(costed, run, 0.05, 20, VALUES)),
        ("economics.lcoc", gm.evaluate.lcoc(costed, run, 0.05, 20, VALUES, on_error="record")),
        ("economics.co2", gm.evaluate.co2(costed, run, VALUES)),
        ("economics.npv", gm.evaluate.npv(costed, run, 0.05, 20, VALUES)),
        ("economics.payback", gm.evaluate.payback(costed, run, VALUES)),
        ("economics.Assumptions", VALUES.model_dump()),
        ("checks.energy_balance", gm.evaluate.energy_balance(replay)),
        ("checks.mass_balance", gm.evaluate.mass_balance(replay)),
        ("checks.bounds", gm.evaluate.bounds(plant, replay)),
        ("checks.run_all", gm.evaluate.run_all(plant, replay)),
        ("testing.check_module", gm.modules.check(Booster, EXAMPLE)),
    ]


def test_every_real_return_is_plain_json(example_run):
    """No NumPy type, no NaN and no infinity anywhere in a result."""
    for name, result in real_calls(example_run):
        text = json.dumps(result, allow_nan=False)
        assert json.loads(text) == result, name


@pytest.mark.parametrize(
    "call",
    [
        lambda: gm.analysis.injectivity(None, "doublet.injector"),
        lambda: gm.analysis.calibrate_pump(None, "doublet.esp", None),
        lambda: gm.analysis.calibrate_corrosion([]),
        lambda: gm.analysis.erosion(None, "doublet"),
    ],
    ids=["injectivity", "calibrate_pump", "calibrate_corrosion", "erosion"],
)
def test_every_name_not_built_raises_not_implemented_yet(call):
    """The final signature exists and the call says its work lands later."""
    with pytest.raises(gm.errors.NotImplementedYet):
        call()
