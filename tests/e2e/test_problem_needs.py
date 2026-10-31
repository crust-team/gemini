"""What a heating and cooling problem needs of gemini: one test per need, each in general terms.

The list is in ``.claude/docs/testing.md``. The demand is a file written here, the plant dict the
design of a sample problem, sized as each test needs.
"""

from copy import deepcopy

import pandas as pd
import pytest

import gemini as gm
from tests.fixtures.sample_problems import sample_json, template_dict

pytestmark = pytest.mark.xdist_group("problem_needs")

HOURS = 12
HEAT_MW = 12.0
COLD_MW = 5.0
RULES = {
    "doublet_flow": {"min": "60 m3/h", "max": "320 m3/h"},
    "max_brine_cooling": "45 K",
}


def sized_dict(doublets):
    """Return the plant dict on ``doublets`` doublets, each with the values of ``d0``."""
    data = deepcopy(template_dict("HeatingCoolingPlant"))
    data["size"] = {"doublets": doublets}
    own = {name: item for name, item in data["params"].items() if not name.startswith(("d0", "d1"))}
    first = {name[3:]: item for name, item in data["params"].items() if name.startswith("d0.")}
    data["params"] = own | {
        f"d{index}.{name}": item for index in range(doublets) for name, item in first.items()
    }
    data["fluids"] = {name: item for name, item in data["fluids"].items() if name != "d1"} | {
        f"d{index}": data["fluids"]["d0"] for index in range(doublets)
    }
    return data


def demand_file(folder):
    """Write an hourly demand in kW under names of its own and return its path."""
    index = pd.date_range("2031-02-03", periods=HOURS, freq="h", tz="UTC")
    frame = pd.DataFrame(
        {"stamp": index, "heat_kw": HEAT_MW * 1000, "cold_kw": COLD_MW * 1000},
    )
    path = folder / "demand.csv"
    frame.to_csv(path, index=False)
    return path


def read_demand(path):
    """Return the demand of the file, as ``gm.schedule`` takes it."""
    columns = {"heat_kw": "heating_demand", "cold_kw": "cooling_demand"}
    return gm.data.from_csv(path, columns, "kW", time_column="stamp")


def run_on(plant, demand, rules=RULES):
    """Return the results of a plan of ``demand`` on ``plant``; a failed step fails the test."""
    return gm.simulate(plant, gm.schedule(plant, demand, rules))


@pytest.fixture(scope="module")
def demand(tmp_path_factory):
    """Return the demand of a file written for this module."""
    return read_demand(demand_file(tmp_path_factory.mktemp("demand")))


@pytest.fixture(scope="module")
def plant():
    """Return the plant on two doublets, not changed by a test."""
    return gm.plants.from_dict(sized_dict(2))


@pytest.fixture(scope="module")
def results(plant, demand):
    """Return one run of the plant on the demand, read by the limit tests."""
    return run_on(plant, demand)


def worst(plant, results, target, **bounds):
    """Return the check of one limit on the run, for each module it matches."""
    limits = gm.evaluate.Limits()
    limits.add(target, **bounds)
    return gm.evaluate.limits(plant, results, limits)


def test_heating_and_cooling_demand_come_from_a_file(demand):
    """Any column names, any unit, a constant step: the demand is in W on a UTC index."""
    assert list(demand) == ["heating_demand", "cooling_demand"]
    assert demand["heating_demand"].iloc[0] == pytest.approx(HEAT_MW * 1e6)
    assert demand["cooling_demand"].iloc[0] == pytest.approx(COLD_MW * 1e6)
    assert str(demand.index.tz) == "UTC"
    assert demand.attrs["units"]["heating_demand"] == "W"


@pytest.mark.parametrize("doublets", [1, 2, 3])
def test_a_plant_runs_on_one_to_three_doublets(demand, doublets):
    """Every step runs, and the first doublet carries flow."""
    plant = gm.plants.from_dict(sized_dict(doublets))
    results = run_on(plant, demand)
    assert results.errors() == []
    assert max(results.get("d0.reservoir", "liquid_flow")["value"]) > 0


def test_a_chosen_depth_sets_the_reservoir():
    """The plant's ``depth`` reaches each doublet, whose geotherm gives its temperature."""
    shallow, deep = sized_dict(2), sized_dict(2)
    shallow["params"]["depth"], deep["params"]["depth"] = "2000 m", "3000 m"
    gradient = gm.units.convert(1, "K/km", "K/m") * 30
    lift = (
        gm.plants.from_dict(deep).d1.reservoir.temperature
        - gm.plants.from_dict(shallow).d1.reservoir.temperature
    )
    assert lift == pytest.approx(gradient * 1000, rel=1e-9)


def test_co_produced_gas_goes_to_the_boiler_before_the_grid(plant, results):
    """The gas of the brine reaches the fuel of the boiler and burns or leaves by the flare."""
    produced = results.get("degasser", "gas_out.chemical_flow")["value"]
    assert min(produced) > 0
    fuel = gm.evaluate.totals(plant, results)
    assert fuel["gas_bought"]["value"] == pytest.approx(0.0, abs=1e-6)
    assert max(results.get("gas_grid", "gas_out.chemical_flow")["value"]) < max(produced)


def test_a_limit_on_the_flow_range_of_each_doublet(plant, results):
    """One check per doublet; a range the run leaves fails."""
    checks = worst(plant, results, "d*.reservoir.liquid_flow", min="60 m3/h", max="320 m3/h")
    assert [item["passed"] for item in checks] == [True, True]
    tight = worst(plant, results, "d*.reservoir.liquid_flow", max="10 m3/h")
    assert not all(item["passed"] for item in tight)


def test_a_limit_on_the_brine_cooling(plant, results):
    """The cooling of the brine from producer to injector, each doublet."""
    checks = worst(plant, results, "d*.brine_cooling", max="45 K")
    assert [item["passed"] for item in checks] == [True, True]


def test_a_limit_on_a_parameter(plant, results):
    """A limit may name a parameter of a design, judged without the run's outputs."""
    checks = worst(plant, results, "d*.pump_efficiency", min=0.6, max=0.8)
    assert [item["passed"] for item in checks] == [True, True]
    assert not worst(plant, results, "d*.pump_efficiency", min=0.9)[0]["passed"]


def test_a_limit_on_the_volume_balance(plant, results):
    """What a doublet produces it injects again."""
    checks = worst(plant, results, "d*.volume_imbalance", min="-1e-6 m3/s", max="1e-6 m3/s")
    assert [item["passed"] for item in checks] == [True, True]


def test_limits_on_the_supply_temperatures(plant, results):
    """The supply at the heat users and at the cold users."""
    heat = worst(plant, results, "heating_consumer.supply_in.temperature", min="95 degC")
    cold = worst(plant, results, "cooling_consumer.supply_in.temperature", max="21 degC")
    assert heat[0]["passed"] and cold[0]["passed"]


def test_a_limit_on_the_operating_time(demand):
    """Each doublet runs the time of the rule, with its outages at whole steps."""
    plant = gm.plants.from_dict(sized_dict(2))
    results = run_on(plant, demand, RULES | {"operating_time": "11 h"})
    checks = gm.evaluate.operating_time(plant, results, "11 h")
    assert [item["passed"] for item in checks] == [True, True]
    assert not gm.evaluate.operating_time(plant, results, "5 h")[0]["passed"]


def test_a_levelised_cost_of_heat_and_cold_together(plant, results):
    """LCTS of the run on stated prices."""
    assumptions = gm.Assumptions(**sample_json("assumptions.json"))
    assert gm.evaluate.lcts(plant, results, assumptions=assumptions)["value"] > 0
