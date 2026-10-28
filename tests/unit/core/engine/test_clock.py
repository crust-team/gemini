"""Finite clock constructor tests."""

import gemini as gm


def test_clock_range_is_inclusive():
    """A one-hour range at 15-minute cadence has five ticks."""
    assert len(gm.Clock.range("2024-01-01", "2024-01-01T01:00Z", "15min")) == 5
