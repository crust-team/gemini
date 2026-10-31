"""``gm.evaluate.operating_time``: the time each doublet ran."""

import pytest

import gemini as gm
from gemini.plants.doublet import Doublet
from tests.fixtures.errors import raises
from tests.fixtures.result_tables import make_results

HOUR = 3600.0
DAY = 86400.0


def doublets():
    """Return a plant of two doublets, never run."""
    plant = gm.Plant("Two")
    plant.add(Doublet, name="d0")
    plant.add(Doublet, name="d1")
    return plant


def run(first, second, step=86400.0):
    """Return results whose doublets carried the given flows."""
    return make_results(
        {
            "d0.reservoir": {"liquid_flow": first},
            "d1.reservoir": {"liquid_flow": second},
        },
        step=step,
    )


def test_each_doublet_gets_a_check_of_its_time():
    """A step with flow counts its duration, in seconds, against the limit."""
    results = run([0.1, 0.1, 0.0], [0.0, 0.1, 0.0])
    checks = gm.evaluate.operating_time(doublets(), results, "2 d")
    assert [item["name"] for item in checks] == ["d0.operating_time", "d1.operating_time"]
    assert [item["passed"] for item in checks] == [True, False]
    assert checks[1]["value"] == {"value": DAY, "unit": "s"}
    assert checks[1]["limit"] == {"value": 2 * DAY, "unit": "s"}


def test_the_same_fraction_on_hourly_and_daily_steps_gives_the_same_verdict():
    """Two thirds of the period is the same time whatever the step: 2 of 3 days, 48 of 72 h."""
    daily = run([0.1, 0.1, 0.0], [0.1, 0.1, 0.0])
    hourly = run([0.1] * 48 + [0.0] * 24, [0.1] * 48 + [0.0] * 24, step=HOUR)
    for results in (daily, hourly):
        checks = gm.evaluate.operating_time(doublets(), results, "2 d")
        assert [item["passed"] for item in checks] == [True, True]
        assert checks[0]["value"]["value"] == 2 * DAY


def test_a_missing_value_is_no_flow():
    """A step with no value does not count."""
    flows = [0.1] * 25 + [float("nan")] * 23
    checks = gm.evaluate.operating_time(doublets(), run(flows, [0.0] * 48, step=HOUR), 25 * HOUR)
    assert checks[0]["passed"] and checks[0]["value"]["value"] == 25 * HOUR
    assert checks[1]["value"]["value"] == 0


def test_half_a_step_of_rounding_passes_but_not_more():
    """The plan rounds to whole steps: 1.5 days of limit accepts 1 or 2 days, not 3."""
    for flows, passed in (([0.1, 0.0, 0.0], True), ([0.1, 0.1, 0.0], True), ([0.1] * 3, False)):
        checks = gm.evaluate.operating_time(doublets(), run(flows, flows), "1.5 d")
        assert checks[0]["passed"] is passed


def test_more_time_than_asked_fails_too():
    """The rule is exact, not a minimum."""
    checks = gm.evaluate.operating_time(doublets(), run([0.1, 0.1], [0.1, 0.1]), "1 d")
    assert not any(item["passed"] for item in checks)


@pytest.mark.parametrize("duration", ["soon", 0])
def test_no_duration_is_refused(duration):
    """A positive duration, no check."""
    with raises(gm.errors.ValidationError, "invalid_value"):
        gm.evaluate.operating_time(doublets(), run([0.1], [0.1]), duration)


@pytest.mark.parametrize("duration", [None, "2 d"])
def test_run_all_adds_them_when_given(duration):
    """``run_all`` takes the duration; without it stays the three checks."""
    report = gm.evaluate.run_all(doublets(), run([0.1, 0.1], [0.1, 0.1]), duration)
    names = [item["name"] for item in report["checks"]]
    assert ("d0.operating_time" in names) == (duration is not None)
