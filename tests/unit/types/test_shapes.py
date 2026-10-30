"""The three return shapes: one helper and one schema each."""

import json
import math

import pytest

import gemini as gm
from gemini.types import shapes
from tests.fixtures import ROOT
from tests.fixtures.json_schema import check

SCHEMAS = ROOT / "docs" / "schemas"


def fits(document, name):
    """Return the problems of a document against the stored schema of a shape."""
    return check(document, json.loads((SCHEMAS / f"{name}.schema.json").read_text()))


def test_a_value_has_its_unit_and_no_reason():
    """A number or an array travels with its unit."""
    assert shapes.value(3.0, "W") == {"value": 3.0, "unit": "W"}
    assert shapes.value([1.0, None], "W") == {"value": [1.0, None], "unit": "W"}
    assert fits(shapes.value(3.0, "W"), "value") == []


@pytest.mark.parametrize("number", [None, math.nan, math.inf])
def test_a_missing_value_says_why(number):
    """``None``, NaN and infinity are null, and a null value always has a reason."""
    assert shapes.value(number, "W", "no flow") == {"value": None, "unit": "W", "reason": "no flow"}
    assert shapes.value(number, "W")["reason"] == shapes.NO_VALUE
    json.dumps(shapes.value(number, "W"), allow_nan=False)
    assert fits(shapes.value(number, "W"), "value") == []


def test_a_null_value_without_a_reason_does_not_fit_the_schema():
    """The schema holds the rule, so a hand-built shape fails."""
    assert fits({"value": None, "unit": "W"}, "value")


def test_details_follow_the_keys_of_the_shape():
    """The fixed keys come first, details after, and a NaN becomes null."""
    result = shapes.value(float("nan"), "EUR", "why", capex=shapes.value(3.0, "EUR"))
    assert list(result) == ["value", "unit", "reason", "capex"]
    assert result["capex"] == {"value": 3.0, "unit": "EUR"}
    json.dumps(result, allow_nan=False)
    assert fits(result, "value") == []


def test_a_series_is_a_value_with_a_time_axis():
    """The key is ``value`` for arrays too."""
    series = shapes.series(["2024-01-01T00:00:00+00:00"], [1.0], "K")
    assert series == {"time": ["2024-01-01T00:00:00+00:00"], "value": [1.0], "unit": "K"}
    assert fits(series, "value") == []


def test_statistics_are_three_values():
    """Each of min, max and mean is a value; one without a number says why."""
    result = shapes.statistics(1.0, 3.0, math.nan, "W")
    assert result["min"] == {"value": 1.0, "unit": "W"}
    assert result["max"] == {"value": 3.0, "unit": "W"}
    assert result["mean"]["value"] is None and result["mean"]["reason"]


def test_a_problem_has_four_keys_and_a_run_row_adds_the_time():
    """There is no class key: ``code`` is the stable key for machines."""
    assert shapes.problem("a.b", "unknown_name", "no such name", ("x",)) == {
        "path": "a.b",
        "code": "unknown_name",
        "message": "no such name",
        "suggestions": ["x"],
    }
    row = shapes.problem("a", "module_error", ValueError("boom"), time="2024-01-01T00:00:00+00:00")
    assert row["time"] == "2024-01-01T00:00:00+00:00" and row["message"] == "boom"
    assert fits(row, "problem") == []


def test_a_decided_check_has_four_keys():
    """name, passed, value and limit, the last two values."""
    result = shapes.check("x", True, shapes.value(1.5, "W"), shapes.value(0.1, "W"))
    assert result == {
        "name": "x",
        "passed": True,
        "value": {"value": 1.5, "unit": "W"},
        "limit": {"value": 0.1, "unit": "W"},
    }
    assert fits(result, "check") == []


def test_an_undecided_check_carries_its_reason_in_the_value_and_stays_json():
    """``passed`` None has a null value with the reason; a NaN value becomes null."""
    measured = shapes.value(float("nan"), "W", "nothing to judge")
    result = shapes.check("x", None, measured, shapes.value(0.1, "W"))
    assert result["passed"] is None and result["value"]["reason"] == "nothing to judge"
    json.dumps(result, allow_nan=False)
    assert fits(result, "check") == []


def test_a_check_with_a_bare_number_does_not_fit_the_schema():
    """``value`` and ``limit`` are values, not numbers."""
    assert fits({"name": "x", "passed": True, "value": 1.5, "limit": 0.1}, "check")


def test_the_problem_of_an_error_is_the_shape():
    """``to_dict`` and the helper give the same keys in the same order."""
    error = gm.errors.ValidationError("bad", path="a", code="invalid_value")
    assert error.to_dict() == shapes.problem("a", "invalid_value", "bad")
    assert fits(error.to_dict(), "problem") == []


def test_the_shapes_export_the_one_problem_helper():
    """``gemini.errors`` is a leaf, so the helper is defined there and exported here."""
    assert shapes.problem is gm.errors.base.problem
