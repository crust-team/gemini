"""Protect the original numerical results with a relative tolerance of 1e-9."""

from tests.fixtures.evaluate import assert_values, evaluate, golden_cases


def test_golden():
    """Compare every captured physics family against the immutable baseline."""
    expected = golden_cases()
    actual = evaluate()
    assert actual.keys() == expected.keys()
    for key in expected:
        assert_values(actual[key]["expected"], expected[key]["expected"])
