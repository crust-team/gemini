"""UTC conversion, durations and tick spacing."""

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest
import pytz

from gemini.utils.time import (
    DEFAULT_STEP,
    interval_seconds,
    median_step,
    parse_duration,
    to_utc,
    to_utc_index,
)


def test_to_utc_treats_naive_values_as_utc_and_converts_aware_values():
    """Strings, naive and aware datetimes all become aware UTC datetimes."""
    expected = datetime(2024, 7, 1, tzinfo=timezone.utc)
    assert to_utc("2024-07-01T00:00:00Z") == expected
    assert to_utc("2024-07-01") == expected
    assert to_utc(datetime(2024, 7, 1)) == expected
    assert to_utc(pd.Timestamp("2024-07-01T02:00:00+02:00")) == expected
    assert to_utc(expected).tzinfo is timezone.utc


def test_parse_duration_accepts_seconds_and_pandas_syntax():
    """Numbers are seconds; strings use pandas syntax; zero and negative steps fail."""
    assert parse_duration(900) == pd.Timedelta(minutes=15)
    assert parse_duration(0.5) == pd.Timedelta(milliseconds=500)
    assert parse_duration("15min") == pd.Timedelta(minutes=15)
    assert parse_duration(timedelta(hours=1)) == pd.Timedelta(hours=1)
    for invalid in (0, -1, "0s"):
        with pytest.raises(ValueError, match="must be positive"):
            parse_duration(invalid)


def test_median_step_and_interval_seconds():
    """Spacing uses the median; the last tick takes the supplied final step."""
    index = pd.DatetimeIndex(
        ["2024-01-01 00:00", "2024-01-01 00:15", "2024-01-01 00:30", "2024-01-01 01:30"], tz="UTC"
    )
    assert median_step(index) == pd.Timedelta(minutes=15)
    assert median_step(index[:1]) is None
    seconds = interval_seconds(index, DEFAULT_STEP)
    np.testing.assert_array_equal(seconds, [900.0, 900.0, 3600.0, 3600.0])
    assert interval_seconds(index[:0], pd.Timedelta(minutes=5)).tolist() == [300.0]


def test_to_utc_index_localises_naive_values_and_keeps_offsets():
    """Naive values are local to ``tz``; offsets may change between values at DST switches."""
    naive = to_utc_index(["2024-07-01 02:00", "2024-07-01 03:00"], "Europe/Oslo")
    assert [t.hour for t in naive] == [0, 1]
    assert str(naive.tz) == "UTC"
    offsets = to_utc_index(["2024-03-31T01:00:00+01:00", "2024-03-31T03:00:00+02:00"])
    assert [t.hour for t in offsets] == [0, 1]
    aware = pd.DatetimeIndex(["2024-01-01 01:00"], tz="Europe/Oslo")
    assert to_utc_index(aware)[0] == pd.Timestamp("2024-01-01 00:00", tz="UTC")
    assert len(to_utc_index([])) == 0
    with pytest.raises(pytz.exceptions.AmbiguousTimeError, match="2024-10-27 02:30"):
        to_utc_index(["2024-10-27 02:30"], "Europe/Oslo")
