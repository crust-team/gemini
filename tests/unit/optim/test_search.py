"""``gm.optim.minimize`` and ``gm.optim.sample`` on a boiler and a heat user."""

import json

import numpy as np
import pandas as pd
import pytest

import gemini as gm
from gemini.optim import search
from tests.fixtures.errors import raises
from tests.unit.analysis.test_schedule import plant_of_two

DEMAND = 1e6
"""Constant heat demand [W]."""
CAPACITY = [{"path": "boiler", "parameter": "capacity", "lower": 2e5, "upper": 3e6}]
PEAK = "boiler.capacity"


def boiler_plant():
    """Return a gas boiler and its heat user, with the heat water named at 60 and 100 degC."""
    plant = gm.Plant("Boiler")
    plant.add("GasGrid", name="grid")
    plant.add("Boiler", name="boiler", params={"capacity": "2 MW", "efficiency": 0.9})
    plant.add(
        "HeatingGrid",
        name="users",
        params={"return_temperature": "60 degC", "return_pressure": "6 bar"},
    )
    plant.connect("grid.gas_out", "boiler.fuel_in")
    plant.connect("users.return_out", "boiler.fluid_in")
    plant.connect("boiler.fluid_out", "users.supply_in")
    plant.connect("boiler.flue_out", "flue")
    plant.connect("boiler.loss_out", "loss")
    plant.get_submodule("users").fluid = gm.WATER
    return plant


def profile():
    """Return two days of the same demand, with flow to spare."""
    index = pd.date_range("2027-01-01", periods=2, freq="D", tz="UTC")
    columns = {
        "users.heat_demand": DEMAND,
        "users.flow": 20.0,
        "boiler.temperature_setpoint": 373.15,
    }
    return pd.DataFrame(columns, index=index)


@pytest.fixture(scope="module")
def half_covered():
    """Return the search for the smallest peak that covers half the demand: half its capacity."""
    constraints = [{"metric": "heating_coverage", "minimum": 0.5}]
    return gm.optim.minimize(
        boiler_plant(), profile(), CAPACITY, "peak_heat", constraints, evaluations=20
    )


def test_minimize_finds_the_optimum_within_the_budget(half_covered):
    """The constraint sets the optimum; the result is plain JSON and ready for ``set_params``."""
    assert half_covered["best"]["parameters"][PEAK] == pytest.approx(DEMAND / 2, rel=0.05)
    assert half_covered["best"]["value"] == pytest.approx(DEMAND / 2, rel=0.05)
    assert half_covered["best"]["unit"] == "W"
    assert half_covered["evaluations"] == len(half_covered["history"]) == 20
    json.dumps(half_covered, allow_nan=False)


def test_a_trial_that_breaks_a_constraint_is_recorded_and_never_best(half_covered):
    """Its reason stays in the history."""
    rejected = [item for item in half_covered["history"] if "reason" in item]
    assert rejected and all("heating_coverage" in item["reason"] for item in rejected)
    assert all(item["parameters"][PEAK] < 0.5 * DEMAND for item in rejected)
    assert half_covered["best"]["parameters"][PEAK] >= 0.5 * DEMAND


def test_a_failed_run_is_recorded_too():
    """A bound of the parameter refuses a trial; the others carry on."""
    variables = [{"path": "boiler", "parameter": "efficiency", "lower": 0.5, "upper": 1.5}]
    result = gm.optim.minimize(boiler_plant(), profile(), variables, "peak_heat", evaluations=10)
    failed = [item for item in result["history"] if "reason" in item]
    assert failed and all(item["parameters"]["boiler.efficiency"] > 1 for item in failed)
    assert all(item["value"] is None for item in failed)
    assert result["best"]["parameters"]["boiler.efficiency"] <= 1


def test_every_trial_failing_leaves_no_best():
    """No value, with the reason."""
    variables = [{"path": "boiler", "parameter": "efficiency", "lower": 1.2, "upper": 1.5}]
    result = gm.optim.minimize(boiler_plant(), profile(), variables, "peak_heat", evaluations=5)
    assert result["best"]["value"] is None and result["best"]["parameters"] is None
    assert "every trial" in result["best"]["reason"]


def test_a_leading_minus_maximises():
    """The value keeps the sign of the metric."""
    variables = [dict(CAPACITY[0], upper=DEMAND)]
    result = gm.optim.minimize(boiler_plant(), profile(), variables, "-peak_heat", evaluations=10)
    assert result["best"]["value"] == pytest.approx(DEMAND, rel=0.1)
    assert result["best"]["value"] == max(item["value"] for item in result["history"])


@pytest.fixture(scope="module")
def repeated():
    """Return a plant, its first state and two equal searches on it."""
    plant = boiler_plant()
    before = plant.to_dict()
    runs = [gm.optim.minimize(plant, profile(), CAPACITY, "peak_heat", evaluations=5)]
    runs.append(gm.optim.minimize(plant, profile(), CAPACITY, "peak_heat", evaluations=5))
    return plant, before, runs


def test_the_same_call_gives_the_same_trials_and_leaves_the_plant_alone(repeated):
    """The search has a fixed seed and works on copies."""
    plant, before, runs = repeated
    assert runs[0] == runs[1] and plant.to_dict() == before


def test_an_economic_metric_reads_the_assumptions():
    """With them a value per year."""
    variables = [dict(CAPACITY[0], lower=DEMAND, upper=2 * DEMAND)]
    values = gm.economics.Assumptions(discount_rate=0.05, lifetime_years=20, gas_price=40.0)
    run = gm.optim.minimize(
        boiler_plant(), profile(), variables, "annualised_cost", evaluations=5, assumptions=values
    )
    assert run["best"]["unit"] == "EUR/year" and "reason" not in run["best"]


def test_an_economic_metric_without_assumptions_gives_the_reason():
    """What is missing is in the history, and no trial is best."""
    variables = [dict(CAPACITY[0], lower=DEMAND, upper=2 * DEMAND)]
    idle = gm.optim.minimize(boiler_plant(), profile(), variables, "lcts", evaluations=5)
    assert "discount_rate" in idle["history"][0]["reason"] and idle["best"]["value"] is None


@pytest.mark.parametrize(
    ("arguments", "code"),
    [
        ({"objective": "lcox"}, "unknown_name"),
        ({"constraints": [{"metric": "cost", "minimum": 0}]}, "unknown_name"),
        ({"variables": []}, "missing_value"),
        ({"variables": [dict(CAPACITY[0], lower=2e6, upper=1e6)]}, "invalid_value"),
        ({"variables": [dict(CAPACITY[0], parameter="capacty")]}, "unknown_name"),
        ({"evaluations": 4}, "invalid_value"),
    ],
)
def test_a_search_that_does_not_fit_is_refused(arguments, code):
    """Before any simulation."""
    call = dict(variables=CAPACITY, objective="peak_heat") | arguments
    with raises(gm.errors.ValidationError, code):
        gm.optim.minimize(boiler_plant(), profile(), **call)


UNCERTAIN = {
    "boiler.capacity": {"kind": "uniform", "lower": 2e5, "upper": 2e6},
    "boiler.efficiency": {"kind": "triangular", "lower": 0.7, "mode": 0.8, "upper": 0.9},
    "users.return_pressure": {"kind": "normal", "mean": 6e5, "std": 1e4},
}


@pytest.fixture(scope="module")
def sampled():
    """Return two samples of one seed."""
    plant = boiler_plant()
    return [gm.optim.sample(plant, profile(), UNCERTAIN, ["peak_heat"], 6, seed=3) for _ in "ab"]


def test_sample_gives_the_same_summary_with_the_same_seed(sampled):
    """Each draw is a simulation; the summary holds the percentiles, in plain JSON."""
    first, second = sampled
    assert first == second
    assert len(first["samples"]) == 6
    spread = first["summary"]["peak_heat"]
    assert set(spread) == {"mean", "p5", "p50", "p95", "unit"} and spread["unit"] == "W"
    numbers = [item["metrics"]["peak_heat"]["value"] for item in first["samples"]]
    assert spread["p50"] == pytest.approx(np.median(numbers))
    assert spread["p5"] <= spread["p50"] <= spread["p95"]
    json.dumps(first, allow_nan=False)


def test_another_seed_gives_other_draws(sampled):
    """Each draw lies inside its uniform limits."""
    other = gm.optim.sample(boiler_plant(), profile(), UNCERTAIN, ["peak_heat"], 3, seed=4)
    assert other["samples"][0]["parameters"] != sampled[0]["samples"][0]["parameters"]
    assert all(2e5 <= item["parameters"]["boiler.capacity"] <= 2e6 for item in other["samples"])


def test_a_draw_that_fails_is_recorded_and_left_out_of_the_summary():
    """An efficiency above one is refused; the other draws count."""
    wide = {"boiler.efficiency": {"kind": "uniform", "lower": 0.6, "upper": 1.4}}
    result = gm.optim.sample(boiler_plant(), profile(), wide, ["peak_heat"], 6, seed=0)
    failed = [item for item in result["samples"] if "reason" in item]
    assert failed and len(failed) < 6
    assert result["summary"]["peak_heat"]["mean"] is not None


def test_a_metric_no_draw_gives_says_so():
    """Nothing to spread: ``None`` with the reason, and the unit of the metric."""
    result = gm.optim.sample(boiler_plant(), profile(), UNCERTAIN, ["peak_cold"], 2)
    spread = result["summary"]["peak_cold"]
    assert spread["mean"] is None and spread["p95"] is None and "reason" in spread


@pytest.mark.parametrize(
    ("arguments", "code"),
    [
        ({"count": 0}, "invalid_value"),
        ({"metrics": ["lcox"]}, "unknown_name"),
        ({"distributions": {"boiler.capacty": UNCERTAIN["boiler.capacity"]}}, "unknown_name"),
        ({"distributions": {"boiler.capacity": {"kind": "beta"}}}, "unknown_name"),
        ({"distributions": {"boiler.capacity": {"kind": "normal", "mean": 1}}}, "missing_value"),
        (
            {"distributions": {"boiler.capacity": {"kind": "normal", "mean": 1, "std": -1}}},
            "invalid_value",
        ),
    ],
)
def test_a_sample_that_does_not_fit_is_refused(arguments, code):
    """Wrong names, kinds and fields."""
    call = dict(distributions=UNCERTAIN, metrics=["peak_heat"], count=2) | arguments
    with raises(gm.errors.ValidationError, code):
        gm.optim.sample(boiler_plant(), profile(), **call)


def scheduled_plant():
    """Return the plant of ``test_schedule``: two doublets, a boiler and a heat user."""
    return plant_of_two()


def two_days():
    """Return two days of demand: a frame ``gm.schedule`` plans, not a plan."""
    index = pd.date_range("2027-01-01", periods=2, freq="D", tz="UTC", name="time")
    return pd.DataFrame({"heating_demand": [5e6, 8e6]}, index=index)


FLOW = {"path": "d0", "parameter": "well_diameter", "lower": 0.2, "upper": 0.3}


def planned(monkeypatch):
    """Return the list of the rules of each ``gm.schedule`` of the search, and record them."""
    calls = []
    real = search.schedule

    def counted(plant, demand, rules):
        calls.append(rules)
        return real(plant, demand, rules)

    monkeypatch.setattr(search, "schedule", counted)
    return calls


def test_a_demand_frame_is_planned_for_each_trial(monkeypatch):
    """A variable that changes the design changes the plan: one schedule per simulation."""
    calls = planned(monkeypatch)
    found = gm.optim.minimize(scheduled_plant(), two_days(), [FLOW], "peak_heat", evaluations=5)
    assert len(calls) == found["evaluations"] == 5
    assert calls[0] == gm.challenge_rules()


def test_a_plan_is_not_planned_again(monkeypatch):
    """A plan stays what it is over the trials, as a run input does."""
    calls = planned(monkeypatch)
    rules = {"doublet_flow": gm.challenge_rules()["doublet_flow"], "max_brine_cooling": "40 K"}
    plan = gm.schedule(scheduled_plant(), two_days(), rules)
    calls.clear()
    uncertain = {"d0.well_diameter": {"kind": "uniform", "lower": 0.2, "upper": 0.3}}
    gm.optim.sample(scheduled_plant(), plan, uncertain, ["peak_heat"], count=2)
    assert calls == []


def test_no_profile_is_the_demand_year_under_the_challenge_rules(monkeypatch):
    """``None`` reads the demand of the challenge, and ``sample`` takes it too."""
    calls = planned(monkeypatch)
    monkeypatch.setattr(search.profiles, "demand", two_days)
    uncertain = {"d0.well_diameter": {"kind": "uniform", "lower": 0.2, "upper": 0.3}}
    found = gm.optim.sample(scheduled_plant(), None, uncertain, ["peak_heat"], count=2)
    assert len(found["samples"]) == 2
    assert calls == [gm.challenge_rules()] * 2
