"""The plant KPIs under fixed names, against hand-computed energies."""

import json
import math

import pytest

import gemini as gm
from tests.fixtures.result_tables import cold_ports, heat_ports, make_results


@pytest.fixture(scope="module")
def plant():
    """Return a plant with one heat and one cooling consumer."""
    plant = gm.Plant("Demo")
    plant.add("HeatingGrid", "heat")
    plant.add("CoolingGrid", "cool")
    plant.add("ElectricityGrid", "grid")
    return plant


@pytest.fixture(scope="module")
def results():
    """Return three hourly ticks: heat 300 of 500 Wh demanded, cold 60 of 80, 150 Wh electricity."""
    return make_results(
        {
            "heat": heat_ports([100, 200, 0]) | {"unmet_demand": [0, 100, 100]},
            "cool": cold_ports([10, 20, 30])
            | {"unmet_sensible": [0, 0, 10], "unmet_latent": [0, 0, 10]},
            "grid": {"power_out": [50, 50, 50]},
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


def test_kpi_is_a_namespace():
    """``compute`` and ``names`` are its functions; it is no function with an attribute."""
    assert not callable(gm.kpi) and gm.kpi.__all__ == ["compute", "names", "totals"]


def test_values_equal_the_hand_computed_ratios(plant, results):
    """Heating 300/500, cooling 60/80, COP 300/150 and the two peaks."""
    kpis = gm.kpi.compute(plant, results)
    assert kpis["heating_coverage"] == {"value": 0.6, "unit": "-"}
    assert kpis["cooling_coverage"]["value"] == 0.75
    assert kpis["cop"]["value"] == 2.0
    assert kpis["peak_heat"] == {"value": 200.0, "unit": "W"}
    assert kpis["peak_cold"]["value"] == 30.0


def test_a_plant_without_consumers_gives_none_with_a_reason(fresh_plant, fast_dataset):
    """The doublet heat plant has no consumer leaf: every KPI is null and says why."""
    window = fast_dataset.window(None, "2024-07-01T01:00:00Z")
    replay = gm.replay(fresh_plant, window)
    kpis = gm.kpi.compute(fresh_plant, replay)
    assert list(kpis) == gm.kpi.names()
    assert all(item["value"] is None and item["reason"] for item in kpis.values())
    json.dumps(kpis, allow_nan=False)


def test_zero_demand_and_zero_electricity_have_reasons(plant):
    """A run with nothing demanded or consumed does not divide by zero."""
    idle = make_results(
        {
            "heat": heat_ports([0.0, 0.0]) | {"unmet_demand": [0.0, 0.0]},
            "grid": {"power_out": [0.0, 0.0]},
        }
    )
    kpis = gm.kpi.compute(plant, idle)
    assert kpis["heating_coverage"]["reason"] == "the demand is zero over the window"
    assert kpis["cop"]["reason"] == "no electricity is consumed over the window"
    assert kpis["cooling_coverage"]["reason"] == "the plant has no CoolingGrid"


def test_skipped_ticks_leave_the_ratios_alone(plant):
    """A tick with no value adds to neither the delivered nor the demanded energy."""
    gap = make_results(
        {
            "heat": heat_ports([100, math.nan]) | {"unmet_demand": [100, math.nan]},
            "grid": {"power_out": [50, 50]},
        }
    )
    assert gm.kpi.compute(plant, gap)["heating_coverage"]["value"] == 0.5


def test_totals_integrate_the_ports_of_the_edge_modules(plant, results):
    """Each total is the hand sum of one edge column; a module the plant lacks says so."""
    totals = gm.kpi.totals(plant, results)
    assert totals["heat_delivered"] == {"value": 300 * 3600.0, "unit": "J"}
    assert totals["cold_delivered"]["value"] == 60 * 3600.0
    assert totals["gas_bought"]["value"] is None and totals["gas_bought"]["reason"]
    json.dumps(totals, allow_nan=False)


def test_totals_of_a_run_with_every_edge_module():
    """Bought, sold, released, wasted and lost come from their own module."""
    plant = gm.Plant("Edges")
    for module, name in (
        ("ElectricityGrid", "grid"),
        ("GasGrid", "gas"),
        ("Atmosphere", "air"),
        ("WasteGrid", "waste"),
        ("ChemicalGrid", "chemicals"),
    ):
        plant.add(module, name)
    run = make_results(
        {
            "grid": {"net_import": [10.0], "net_export": [1.0]},
            "gas": {"gas_out.chemical_flow": [20.0]},
            "air": {"co2_emission": [2.0], "methane_emission": [0.5], "heat_in": [7.0]},
            "waste": {"waste_in.mass_flow": [3.0]},
            "chemicals": {"chemical_out.mass_flow": [4.0]},
        }
    )
    totals = {name: item["value"] for name, item in gm.kpi.totals(plant, run).items()}
    assert totals == {
        "heat_delivered": None,
        "cold_delivered": None,
        "electricity_bought": 36000.0,
        "electricity_sold": 3600.0,
        "gas_bought": 72000.0,
        "co2_emitted": 7200.0,
        "methane_emitted": 1800.0,
        "waste": 10800.0,
        "chemicals": 14400.0,
        "losses": 25200.0,
    }
