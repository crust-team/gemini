"""Timestamps, UTC conversion, tick spacing and durations.

Every timestamp inside GEMINI is timezone-aware UTC. Naive input is interpreted in a caller
chosen zone (UTC by default) and rejected when ambiguous or nonexistent at a DST switch.
"""

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


def parse_duration(step):
    """Parse a positive duration given as seconds or as pandas syntax such as ``"15min"``."""
    if isinstance(step, (int, float)):
        value = pd.Timedelta(seconds=step)
    else:
        value = pd.Timedelta(step)
    if pd.isna(value) or value <= pd.Timedelta(0):
        raise ValueError(f"Clock step must be positive, got {step!r}")
    return value


def median_step(index):
    """Return the median spacing of a ``DatetimeIndex`` as ``pd.Timedelta``, or ``None``."""
    if len(index) < 2:
        return None
    return pd.Timedelta(int(np.median(np.diff(index.asi8))), unit="ns")


def interval_seconds(index, final_step):
    """Return seconds from each tick to the next, using ``final_step`` after the last tick."""
    return np.append(np.diff(index.asi8) / 1e9, pd.Timedelta(final_step).total_seconds())
