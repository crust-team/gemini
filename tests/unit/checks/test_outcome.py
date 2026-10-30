"""The shape of a check."""

import json

from gemini.checks.outcome import check


def test_a_decided_check_has_four_keys():
    """name, passed, value and tolerance, and no reason."""
    assert check("x", True, 1.5, 0.1) == {
        "name": "x",
        "passed": True,
        "value": 1.5,
        "tolerance": 0.1,
    }


def test_an_undecided_check_carries_its_reason_and_stays_json():
    """``passed`` None adds the reason; a NaN value becomes null."""
    result = check("x", None, float("nan"), 0.1, "nothing to judge")
    assert result["passed"] is None and result["reason"] == "nothing to judge"
    json.dumps(result, allow_nan=False)
