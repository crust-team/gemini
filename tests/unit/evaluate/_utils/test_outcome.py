"""What an economics function does when the inputs cannot give its value."""

import pytest

import gemini as gm
from gemini.evaluate._utils import outcome
from tests.fixtures.errors import raises


def test_an_unavailable_value_raises_by_default():
    """The default of every economics function is to raise, with the code ``no_value``."""
    with raises(gm.errors.ValidationError, "no_value", match="no heat"):
        outcome.unavailable("EUR", "no heat", "raise")


def test_recorded_it_is_none_with_the_reason_and_its_details():
    """Nothing is raised and the parts that are known stay."""
    detail = {"value": 1.0, "unit": "EUR"}
    result = outcome.unavailable("EUR", "no heat", "record", capex=detail)
    assert result == {"value": None, "unit": "EUR", "reason": "no heat", "capex": detail}


def _fails():
    raise gm.errors.ValidationError("no price", code="missing_value")


def test_reported_raises_or_records_a_failure():
    """A failure of the computation follows ``on_error``."""
    with raises(gm.errors.ValidationError, "missing_value"):
        outcome.reported("raise", "EUR", _fails)
    recorded = outcome.reported("record", "EUR", _fails)
    assert recorded == {"value": None, "unit": "EUR", "reason": "no price"}


def test_reported_refuses_another_policy():
    """``on_error`` has two values, everywhere."""
    with pytest.raises(gm.errors.ValidationError, match="on_error"):
        outcome.reported("ignore", "EUR", lambda: None)
