"""Timestamps, UTC conversion, tick spacing and durations.

Every timestamp inside GEMINI is timezone-aware UTC. Naive input is interpreted in a caller
chosen zone (UTC by default) and rejected when ambiguous or nonexistent at a DST switch.
"""

import numbers
import re
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

DEFAULT_STEP = timedelta(hours=1)
"""Interval assumed after the final tick when fewer than two ticks give no spacing."""

EARLIEST = datetime.min.replace(tzinfo=timezone.utc)
"""The earliest UTC instant: the sort key of an undated snapshot."""


def to_utc(value):
    """Return a timezone-aware UTC ``datetime``; naive values and strings are taken as UTC.

    Accepts ISO-8601 text, ``datetime`` and ``pandas.Timestamp``; a bare ``date`` or a number has
    no time of day or zone and raises ``TypeError``.
    """
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime):
        raise TypeError(
            f"timestamp = {value!r} ({type(value).__name__}); expected ISO-8601 text or a datetime"
        )
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def to_utc_index(values, tz="UTC"):
    """Return timestamps as a UTC ``DatetimeIndex``.

    Naive values are local times in ``tz`` and fail when ambiguous or nonexistent at a DST
    switch. Values with UTC offsets keep their own offsets, which may differ between values
    because exported local data changes offset at every DST switch.
    """
    if not isinstance(values, pd.DatetimeIndex) and len(values):
        first = pd.Timestamp(pd.Index(values)[0])
        if first.tzinfo is not None:
            return pd.DatetimeIndex(pd.to_datetime(values, format="mixed", utc=True))
    index = pd.DatetimeIndex(pd.to_datetime(values, format="mixed"))
    if index.tz is None:
        index = index.tz_localize(tz, ambiguous="raise", nonexistent="raise")
    return index.tz_convert("UTC")


_DAY_UNIT = re.compile(r"(?<=[\d\s])d$")
"""The unit ``d`` at the end of a duration text."""


def to_timedelta(step):
    """Parse a positive duration given as seconds or as pandas syntax such as ``"15min"``.

    Any real number counts as seconds, including NumPy scalars such as ``np.int64(900)``, which
    ``pd.Timedelta`` alone would read as nanoseconds. A text may end in ``d`` for days, which
    pandas deprecates.
    """
    if isinstance(step, numbers.Real):
        value = pd.Timedelta(seconds=step.item() if isinstance(step, np.generic) else step)
    else:
        value = pd.Timedelta(_DAY_UNIT.sub("D", step) if isinstance(step, str) else step)
    if pd.isna(value) or value <= pd.Timedelta(0):
        raise ValueError(f"duration = {step!r}; expected a positive duration")
    return value


def median_step(index):
    """Return the median spacing of a ``DatetimeIndex`` as ``pd.Timedelta``, or ``None``.

    The index may have any resolution; spacing is computed in nanoseconds.
    """
    if len(index) < 2:
        return None
    return pd.Timedelta(int(np.median(np.diff(index.as_unit("ns").asi8))), unit="ns")


def interval_seconds(index, final_step):
    """Return seconds from each tick to the next, using ``final_step`` after the last tick.

    The index may have any resolution; spacing is computed in nanoseconds.
    """
    spacing = np.diff(index.as_unit("ns").asi8) / 1e9
    return np.append(spacing, pd.Timedelta(final_step).total_seconds())
