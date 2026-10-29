"""Timestamps, UTC conversion, tick spacing and durations.

Every timestamp inside GEMINI is timezone-aware UTC. Naive input is interpreted in a caller
chosen zone (UTC by default) and rejected when ambiguous or nonexistent at a DST switch.
"""

import numbers
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

DEFAULT_STEP = timedelta(hours=1)
"""Interval assumed after the final tick when fewer than two ticks give no spacing."""


def to_utc(value):
    """Return a timezone-aware UTC ``datetime``; naive values and strings are taken as UTC."""
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
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


def parse_duration(step):
    """Parse a positive duration given as seconds or as pandas syntax such as ``"15min"``.

    Any real number counts as seconds, including NumPy scalars such as ``np.int64(900)``, which
    ``pd.Timedelta`` alone would read as nanoseconds.
    """
    if isinstance(step, numbers.Real):
        value = pd.Timedelta(seconds=step.item() if isinstance(step, np.generic) else step)
    else:
        value = pd.Timedelta(step)
    if pd.isna(value) or value <= pd.Timedelta(0):
        raise ValueError(f"duration = {step!r}; expected a positive duration")
    return value


def median_step(index):
    """Return the median spacing of a ``DatetimeIndex`` as ``pd.Timedelta``, or ``None``."""
    if len(index) < 2:
        return None
    return pd.Timedelta(int(np.median(np.diff(index.asi8))), unit="ns")


def interval_seconds(index, final_step):
    """Return seconds from each tick to the next, using ``final_step`` after the last tick."""
    return np.append(np.diff(index.asi8) / 1e9, pd.Timedelta(final_step).total_seconds())
