"""Finite clocks: constructors, DST calendars, tick lookup and checkpoint descriptors."""

import pandas as pd

import gemini as gm
from tests.fixtures.errors import raises


def test_clock_range_is_inclusive():
    """A one-hour range at 15-minute cadence has five ticks."""
    assert len(gm.engine.Clock.range("2024-01-01", "2024-01-01T01:00Z", "15min")) == 5


def test_daily_calendar_clocks_keep_local_midnight_across_dst():
    """Bug E-engine-003: daily DST calendars lost a day or moved summer ticks to 01:00 local."""
    days = gm.engine.Clock.days(2024, 3, 30, days=3, step="1D", tz="Europe/Oslo")
    local = [t.tz_convert("Europe/Oslo") for t in days.ticks]
    assert [t.strftime("%m-%d %H:%M") for t in local] == [
        "03-30 00:00",
        "03-31 00:00",
        "04-01 00:00",
    ]
    year = gm.engine.Clock.year(2024, step="1D", tz="Europe/Oslo")
    assert len(year) == 366
    assert {t.tz_convert("Europe/Oslo").hour for t in year.ticks} == {0}
    assert gm.engine.Clock.reopen(year.describe()).ticks.equals(year.ticks)


def test_ticks_must_increase_and_lookups_name_the_clock_range():
    """Unordered ticks and timestamps off the clock raise RunError with the values."""
    with raises(gm.errors.RunError, "clock", match="2024-01-01T00:00:00"):
        gm.engine.Clock(["2024-01-01T01:00Z", "2024-01-01T00:00Z"])
    clock = gm.engine.Clock.range("2024-01-01", "2024-01-01T01:00Z", "30min")
    assert clock.dt("2024-01-01T01:00Z") == 1800.0
    with raises(gm.errors.RunError, "clock", match="t = 2024-01-01T00:10:00"):
        clock.dt("2024-01-01T00:10Z")
    with raises(gm.errors.RunError, "checkpoint", match="kind = 'weekly'"):
        gm.engine.Clock.reopen({"kind": "weekly"})
    with raises(gm.errors.RunError, "clock", match="days = 0"):
        gm.engine.Clock.days(2024, 1, 1, days=0)


def test_single_ticks_window_and_from_data():
    """One tick uses DEFAULT_STEP; windows keep the step; data clocks follow the rows."""
    assert gm.engine.Clock(["2024-01-01"]).dt("2024-01-01") == 3600.0
    clock = gm.engine.Clock.range("2024-01-01", "2024-01-01T02:00Z", "30min")
    window = clock.window("2024-01-01T00:30Z", "2024-01-01T01:00Z")
    assert len(window) == 2 and window.step == pd.Timedelta(minutes=30)
    index = pd.DatetimeIndex(["2024-01-01 00:00", "2024-01-01 00:10", "2024-01-01 00:30"], tz="UTC")
    data = gm.Dataset.from_frame(pd.DataFrame({"x": [1, 2, 3]}, index=index))
    assert gm.engine.Clock.from_data(data).ticks.equals(index)
    assert len(gm.engine.Clock.from_data(data, step="5min")) == 7
    assert len(gm.engine.Clock.from_data(data.window(end="2023-01-01"))) == 0
