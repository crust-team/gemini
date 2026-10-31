"""Limits on the outputs of a run: patterns, worst values and a plain dictionary."""

import json

import pandas as pd
import pytest

import gemini as gm
from gemini.evaluate import Limits
from tests.fixtures.errors import raises
from tests.unit.run.test_schedule import FULL, RULES, demand, plant_of_two


@pytest.fixture(scope="module")
def run():
    """Return the plant of two doublets and a run with a day each doublet is off."""
    plant = plant_of_two()
    plan = gm.schedule(plant, demand(1.5 * FULL, 0.5 * FULL), RULES)
    return plant, gm.simulate(plant, plan)


def by_name(checks):
    """Return the checks by name."""
    return {item["name"]: item for item in checks}


def test_a_doublet_reports_its_flow_and_brine_cooling(run):
    """Volume flow, and the temperature its brine lost between the wells."""
    plant, results = run
    limits = Limits().add("d*.reservoir.liquid_flow", min="50 m3/h", max="300 m3/h")
    limits.add("d*.brine_cooling", max="40 K")
    found = by_name(gm.evaluate.limits(plant, results, limits))
    assert set(found) == {
        "d0.reservoir.liquid_flow",
        "d1.reservoir.liquid_flow",
        "d0.brine_cooling",
        "d1.brine_cooling",
    }
    assert (
        found["d0.reservoir.liquid_flow"]["passed"] is True
        and found["d0.reservoir.liquid_flow"]["value"]["unit"] == "m3/s"
    )
    assert found["d0.reservoir.liquid_flow"]["value"]["value"] == pytest.approx(300 / 3600)
    assert found["d0.reservoir.liquid_flow"]["limit"]["value"] == pytest.approx(
        [50 / 3600, 300 / 3600]
    )
    assert 0 < found["d0.brine_cooling"]["value"]["value"] < 40


def test_a_doublet_at_rest_is_not_held_to_its_minimum_flow(run):
    """The minimum holds while it runs: the off day of the second doublet does not count."""
    plant, results = run
    found = by_name(
        gm.evaluate.limits(plant, results, Limits().add("d1.reservoir.liquid_flow", min="50 m3/h"))
    )
    assert found["d1.reservoir.liquid_flow"]["passed"] is True
    assert found["d1.reservoir.liquid_flow"]["value"]["value"] == pytest.approx(150 / 3600)


def test_a_violated_limit_is_an_answer(run):
    """The worst value comes back; nothing is raised."""
    plant, results = run
    found = gm.evaluate.limits(
        plant, results, Limits().add("d0.reservoir.liquid_flow", max="100 m3/h")
    )
    assert found[0]["passed"] is False
    assert found[0]["value"]["value"] == pytest.approx(300 / 3600)


def test_a_leaf_output_and_a_temperature_limit(run):
    """A limit in degrees converts to the unit of the output."""
    plant, results = run
    limits = Limits().add("users.supply_in.temperature", min="100 degC")
    (found,) = gm.evaluate.limits(plant, results, limits)
    assert found["limit"] == {"value": pytest.approx(373.15), "unit": "K"}
    assert found["passed"] is True


def test_both_limits_report_the_value_furthest_out(run):
    """Between the two limits the larger excursion is the worst."""
    plant, results = run
    (found,) = gm.evaluate.limits(
        plant, results, Limits().add("d0.reservoir.liquid_flow", min=0.05, max=0.06)
    )
    assert found["passed"] is False and found["value"]["value"] == pytest.approx(300 / 3600)


def test_a_pattern_that_matches_nothing_suggests():
    """An unmatched pattern or output is ``unknown_name``, with what exists."""
    plant = plant_of_two()
    with raises(gm.errors.ValidationError, "unknown_name") as caught:
        limits = Limits().add("usrs.unmet_demand", max=1.0)
        gm.evaluate.limits(plant, _empty_results(), limits)
    assert "users" in caught.value.suggestions
    with raises(gm.errors.ValidationError, "unknown_name") as caught:
        gm.evaluate.limits(plant, _empty_results(), Limits().add("users.unmet_demnd", max=1.0))
    assert "unmet_demand" in caught.value.suggestions


def _empty_results():
    """Return an object that stands for results a failed match never reads."""
    return type("Results", (), {"to_frame": staticmethod(pd.DataFrame)})


def test_units_are_checked_when_a_limit_is_added():
    """No plant is needed for that."""
    with raises(gm.errors.ValidationError, "invalid_unit"):
        Limits().add("d*.reservoir.liquid_flow", max="300 m3/parsec")


def test_a_limit_needs_a_bound_and_an_output():
    """The target has a pattern and an output; a limit has at least one bound."""
    with raises(gm.errors.ValidationError, "missing_value"):
        Limits().add("d*.reservoir.liquid_flow")
    with raises(gm.errors.ValidationError, "invalid_value"):
        Limits().add("flow", max=1.0)


def test_limits_round_trip_through_a_plain_dictionary(run):
    """Stored as JSON and read back, they give the same checks."""
    plant, results = run
    limits = Limits().add("d*.reservoir.liquid_flow", min="50 m3/h", max="300 m3/h")
    limits.add("users.supply_in.temperature", min="100 degC")
    stored = json.loads(json.dumps(limits.to_dict()))
    assert Limits.from_dict(stored).to_dict() == limits.to_dict()
    assert gm.evaluate.limits(plant, results, Limits.from_dict(stored)) == gm.evaluate.limits(
        plant, results, limits
    )


def test_a_port_field_of_a_plant_reads_by_path(run):
    """``results[path]`` reads a port field as a plant's output path names it."""
    _, results = run
    assert (results["d0.riser.wellhead_out.T"] > 0).all()


def test_a_parameter_limit_passes_and_fails(run):
    """A design value is judged once, against its value in the run."""
    plant, results = run
    limits = Limits().add("d*.pump_efficiency", min=0.6).add("d0.pump_efficiency", min=0.8)
    found = gm.evaluate.limits(plant, results, limits)
    assert [item["passed"] for item in found] == [True, True, False]
    assert found[-1]["name"] == "d0.pump_efficiency"
    assert found[-1]["value"] == {"value": 0.7, "unit": "-"}
    assert found[-1]["limit"] == {"value": 0.8, "unit": "-"}


def test_a_parameter_limit_takes_a_unit(run):
    """The limit converts to the unit of the parameter."""
    plant, results = run
    found = gm.evaluate.limits(plant, results, Limits().add("d0.depth", max="3 km"))
    assert found[0]["passed"] is True and found[0]["value"]["value"] == 2500


def test_a_parameter_that_changes_is_judged_at_each_date_of_the_run(run):
    """The worst value of a date inside the run counts, and one after it does not."""
    plant, results = run
    dated = gm.plants.from_dict(plant.to_dict())
    dated.set_params("d0", {"pump_efficiency": 0.5}, valid_from="2027-01-02")
    dated.set_params("d0", {"pump_efficiency": 0.1}, valid_from="2030-01-01")
    found = gm.evaluate.limits(dated, results, Limits().add("d0.pump_efficiency", min=0.6))
    assert found[0]["passed"] is False and found[0]["value"]["value"] == 0.5


def test_a_parameter_without_a_value_has_nothing_to_judge(run):
    """An unset design value is no failure."""
    plant, results = run
    limits = Limits().add("users.minimum_return_temperature", min="1 degC")
    assert gm.evaluate.limits(plant, results, limits)[0]["passed"] is None


def test_a_run_with_no_rows_gives_no_verdict_on_any_limit():
    """Every row failed, so there are no columns: each limit answers, none raises a KeyError."""
    plant = plant_of_two()
    plan = gm.schedule(plant, demand(FULL), RULES).drop(columns=["users.flow"])
    plan["users.flow"] = -1.0
    results = gm.simulate(plant, plan, on_error="record")
    limits = Limits().add("d*.reservoir.liquid_flow", min="50 m3/h")
    limits.add("boiler.fluid_out.temperature", min="100 degC")
    limits.add("d0.brine_cooling", max="40 K")
    found = gm.evaluate.limits(plant, results, limits)
    assert len(found) == 4
    for item in found:
        assert item["passed"] is None and item["value"]["value"] is None
        assert item["value"]["reason"].startswith("no_value")
