"""Limits on the outputs of a run: patterns, worst values and a plain dictionary."""

import json

import pandas as pd
import pytest

import gemini as gm
from gemini.checks import Limits
from tests.fixtures.errors import raises
from tests.unit.analysis.test_schedule import FULL, RULES, demand, plant_of_two


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
    limits = Limits().add("d*.flow", min="50 m3/h", max="300 m3/h")
    limits.add("d*.brine_cooling", max="40 K")
    found = by_name(gm.checks.limits(plant, results, limits))
    assert set(found) == {"d0.flow", "d1.flow", "d0.brine_cooling", "d1.brine_cooling"}
    assert found["d0.flow"]["passed"] is True and found["d0.flow"]["value"]["unit"] == "m3/s"
    assert found["d0.flow"]["value"]["value"] == pytest.approx(300 / 3600)
    assert found["d0.flow"]["limit"]["value"] == pytest.approx([50 / 3600, 300 / 3600])
    assert 0 < found["d0.brine_cooling"]["value"]["value"] < 40


def test_a_doublet_at_rest_is_not_held_to_its_minimum_flow(run):
    """The minimum holds while it runs: the off day of the second doublet does not count."""
    plant, results = run
    found = by_name(gm.checks.limits(plant, results, Limits().add("d1.flow", min="50 m3/h")))
    assert found["d1.flow"]["passed"] is True
    assert found["d1.flow"]["value"]["value"] == pytest.approx(150 / 3600)


def test_a_violated_limit_is_an_answer(run):
    """The worst value comes back; nothing is raised."""
    plant, results = run
    found = gm.checks.limits(plant, results, Limits().add("d0.flow", max="100 m3/h"))
    assert found[0]["passed"] is False
    assert found[0]["value"]["value"] == pytest.approx(300 / 3600)


def test_a_leaf_output_and_a_temperature_limit(run):
    """A limit in degrees converts to the unit of the output."""
    plant, results = run
    limits = Limits().add("users.supply_in_T", min="100 degC")
    (found,) = gm.checks.limits(plant, results, limits)
    assert found["limit"] == {"value": pytest.approx(373.15), "unit": "K"}
    assert found["passed"] is True


def test_both_limits_report_the_value_furthest_out(run):
    """Between the two limits the larger excursion is the worst."""
    plant, results = run
    (found,) = gm.checks.limits(plant, results, Limits().add("d0.flow", min=0.05, max=0.06))
    assert found["passed"] is False and found["value"]["value"] == pytest.approx(300 / 3600)


def test_a_pattern_that_matches_nothing_suggests():
    """An unmatched pattern or output is ``unknown_name``, with what exists."""
    plant = plant_of_two()
    with raises(gm.errors.ValidationError, "unknown_name") as caught:
        limits = Limits().add("usrs.heat_supplied", max=1.0)
        gm.checks.limits(plant, _empty_results(), limits)
    assert "users" in caught.value.suggestions
    with raises(gm.errors.ValidationError, "unknown_name") as caught:
        gm.checks.limits(plant, _empty_results(), Limits().add("users.heat_suplied", max=1.0))
    assert "heat_supplied" in caught.value.suggestions


def _empty_results():
    """Return an object that stands for results a failed match never reads."""
    return type("Results", (), {"to_frame": staticmethod(pd.DataFrame)})


def test_units_are_checked_when_a_limit_is_added():
    """No plant is needed for that."""
    with raises(gm.errors.ValidationError, "invalid_unit"):
        Limits().add("d*.flow", max="300 m3/parsec")


def test_a_limit_needs_a_bound_and_an_output():
    """The target has a pattern and an output; a limit has at least one bound."""
    with raises(gm.errors.ValidationError, "missing_value"):
        Limits().add("d*.flow")
    with raises(gm.errors.ValidationError, "invalid_value"):
        Limits().add("flow", max=1.0)


def test_limits_round_trip_through_a_plain_dictionary(run):
    """Stored as JSON and read back, they give the same checks."""
    plant, results = run
    limits = Limits().add("d*.flow", min="50 m3/h", max="300 m3/h")
    limits.add("users.supply_in_T", min="100 degC")
    stored = json.loads(json.dumps(limits.to_dict()))
    assert Limits.from_dict(stored).to_dict() == limits.to_dict()
    assert gm.checks.limits(plant, results, Limits.from_dict(stored)) == gm.checks.limits(
        plant, results, limits
    )
