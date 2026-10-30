"""The plant KPIs under fixed names, against hand-computed energies."""

import json
import math

import pytest

import gemini as gm
from tests.fixtures.result_tables import make_results


@pytest.fixture(scope="module")
def plant():
    """Return a plant with one heat and one cooling consumer."""
    plant = gm.Plant("Demo")
    plant.add("HeatConsumer", "heat")
    plant.add("CoolingConsumer", "cool")
    return plant


@pytest.fixture(scope="module")
def results():
    """Return three hourly ticks: heat 300 of 500 Wh demanded, cold 60 of 80, 150 Wh electricity."""
    return make_results(
        {
            "heat": {"heat_supplied": [100, 200, 0], "unmet_demand": [0, 100, 100]},
            "cool": {
                "heat_absorbed": [10, 20, 30],
                "unmet_sensible": [0, 0, 10],
                "unmet_latent": [0, 0, 10],
            },
            "pump": {"electricity": [50, 50, 50]},
        }
    )


def test_names_are_fixed():
    """The five required names come in the documented order."""
    assert gm.kpi.names() == [
        "heating_coverage",
        "cooling_coverage",
        "cop",
        "peak_heat",
        "peak_cold",
    ]


def test_values_equal_the_hand_computed_ratios(plant, results):
    """Heating 300/500, cooling 60/80, COP 300/150 and the two peaks."""
    kpis = gm.kpi(plant, results)
    assert kpis["heating_coverage"] == {"value": 0.6, "unit": "-"}
    assert kpis["cooling_coverage"]["value"] == 0.75
    assert kpis["cop"]["value"] == 2.0
    assert kpis["peak_heat"] == {"value": 200.0, "unit": "W"}
    assert kpis["peak_cold"]["value"] == 30.0


def test_a_plant_without_consumers_gives_none_with_a_reason(fresh_plant, fast_dataset):
    """The doublet heat plant has no consumer leaf: every KPI is null and says why."""
    window = fast_dataset.window(None, "2024-07-01T01:00:00Z")
    replay = gm.replay(fresh_plant, window)
    kpis = gm.kpi(fresh_plant, replay)
    assert list(kpis) == gm.kpi.names()
    assert all(item["value"] is None and item["reason"] for item in kpis.values())
    json.dumps(kpis, allow_nan=False)


def test_zero_demand_and_zero_electricity_have_reasons(plant):
    """A run with nothing demanded or consumed does not divide by zero."""
    idle = make_results(
        {
            "heat": {"heat_supplied": [0.0, 0.0], "unmet_demand": [0.0, 0.0]},
            "pump": {"electricity": [0.0, 0.0]},
        }
    )
    kpis = gm.kpi(plant, idle)
    assert kpis["heating_coverage"]["reason"] == "the demand is zero over the window"
    assert kpis["cop"]["reason"] == "no electricity is consumed over the window"
    assert kpis["cooling_coverage"]["reason"] == "the plant has no CoolingConsumer"


def test_skipped_ticks_leave_the_ratios_alone(plant):
    """A tick with no value adds to neither the delivered nor the demanded energy."""
    gap = make_results(
        {
            "heat": {"heat_supplied": [100, math.nan], "unmet_demand": [100, math.nan]},
            "pump": {"electricity": [50, 50]},
        }
    )
    assert gm.kpi(plant, gap)["heating_coverage"]["value"] == 0.5
