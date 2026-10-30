"""The shape of an economics return."""

import json

from gemini.economics.outcome import outcome


def test_outcome_has_value_unit_reason_and_details():
    """The fixed keys come first, details after, and a NaN becomes null."""
    result = outcome(float("nan"), "EUR", "why", capex=3.0)
    assert result == {"value": None, "unit": "EUR", "reason": "why", "capex": 3.0}
    json.dumps(result, allow_nan=False)
