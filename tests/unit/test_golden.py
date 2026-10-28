"""Protect the original numerical results with a relative tolerance of 1e-9."""

import json
from pathlib import Path

import pytest

from tests.fixtures.evaluate import evaluate


def assert_values(actual, expected):
    """Recursively compare numeric leaves, keeping strings and nulls exact."""
    if isinstance(expected, dict):
        assert actual.keys() == expected.keys()
        for key in expected:
            assert_values(actual[key], expected[key])
    elif isinstance(expected, list):
        assert len(actual) == len(expected)
        for left, right in zip(actual, expected):
            assert_values(left, right)
    elif isinstance(expected, (int, float)):
        assert actual == pytest.approx(expected, rel=1e-9, abs=0)
    else:
        assert actual == expected


def test_golden():
    """Compare every captured physics family against the immutable baseline."""
    expected = json.loads((Path(__file__).parents[1] / "fixtures/golden_values.json").read_text())
    actual = evaluate()
    assert actual.keys() == expected.keys()
    for key in expected:
        assert_values(actual[key]["expected"], expected[key]["expected"])
