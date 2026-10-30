"""All checks together."""

import pytest

import gemini as gm
from gemini.checks import suite
from tests.fixtures.costed_plants import heating_plant
from tests.fixtures.result_tables import make_results


def test_run_all_lists_the_three_checks():
    """The ledgers and the bounds, in order, and a passing verdict."""
    results = make_results({"heat": {"heat_supplied": [1.0], "return_out_T": [300.0]}})
    report = gm.checks.run_all(heating_plant(), results)
    assert [item["name"] for item in report["checks"]] == [
        "energy_balance",
        "mass_balance",
        "bounds",
    ]
    assert [item["passed"] for item in report["checks"]] == [True, None, True]
    assert report["passed"] is True


def test_one_failure_fails_the_run():
    """A negative heat loss fails the energy ledger and the whole report."""
    results = make_results({"heat": {"heat_loss": [-1.0], "return_out_T": [300.0]}})
    assert gm.checks.run_all(heating_plant(), results)["passed"] is False


@pytest.mark.parametrize(
    "verdicts,expected",
    [([True, None], True), ([None, None], None), ([True, False, None], False)],
)
def test_the_verdict_is_false_with_any_failure_and_true_only_with_a_pass(verdicts, expected):
    """False wins, then True, else undecided."""
    assert suite._verdict(verdicts) is expected
