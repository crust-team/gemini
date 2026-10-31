"""``gm.checks.operating_days``: the days each doublet ran."""

import pytest

import gemini as gm
from gemini.modules.plants.doublet import Doublet
from tests.fixtures.result_tables import make_results

HOUR = 3600.0


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


def test_each_doublet_gets_a_check_of_its_days():
    """A day with flow counts, in the unit ``day`` and against the limit."""
    checks = gm.checks.operating_days(doublets(), run([0.1, 0.1, 0.0], [0.0, 0.1, 0.0]), 2)
    assert [item["name"] for item in checks] == ["d0.operating_days", "d1.operating_days"]
    assert [item["passed"] for item in checks] == [True, False]
    assert checks[1]["value"] == {"value": 1, "unit": "day"}
    assert checks[1]["limit"] == {"value": 2, "unit": "day"}


def test_a_day_counts_once_whatever_its_ticks():
    """Hourly ticks count their day; a missing value is no flow."""
    flows = [0.1] * 25 + [float("nan")] * 23
    checks = gm.checks.operating_days(doublets(), run(flows, [0.0] * 48, step=HOUR), 2)
    assert checks[0]["value"]["value"] == 2 and checks[1]["value"]["value"] == 0


def test_more_days_than_asked_fail_too():
    """The rule is exact, not a minimum."""
    checks = gm.checks.operating_days(doublets(), run([0.1, 0.1], [0.1, 0.1]), 1)
    assert not any(item["passed"] for item in checks)


@pytest.mark.parametrize("days", [None, 2])
def test_run_all_adds_them_when_given(days):
    """``run_all`` takes the days; without them it stays the three checks."""
    report = gm.checks.run_all(doublets(), run([0.1, 0.1], [0.1, 0.1]), days)
    names = [item["name"] for item in report["checks"]]
    assert ("d0.operating_days" in names) == (days is not None)
