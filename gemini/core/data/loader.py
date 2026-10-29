"""Chunked time alignment; this sampler has no dependency on engine clocks."""

from datetime import datetime, timedelta
from typing import NamedTuple

import numpy as np
import pandas as pd

from gemini.utils.time import DEFAULT_STEP, interval_seconds


class Sample(NamedTuple):
    """One aligned observation and explicit missing-data information."""

    t: datetime
    dt: float
    row: dict
    missing: tuple[str, ...]
    gap: bool


class Loader:
    """Align raw rows to any finite tick iterable with bounded source reads."""

    def __init__(
        self, dataset, ticks, columns=None, align="previous", max_gap=None, chunk=timedelta(days=7)
    ):
        """Select exact, previous, or left-closed mean bins; stale holds become missing."""
        if align not in {"exact", "previous", "mean"}:
            raise ValueError(f"Unknown alignment {align!r}")
        self.dataset, self.ticks, self.align = dataset, ticks, align
        self.columns = tuple(dataset.names if columns is None else columns)
        absent = sorted(set(self.columns) - set(dataset.names))
        if absent:
            raise ValueError(f"Dataset is missing bound columns: {', '.join(absent)}")
        self.max_gap = pd.Timedelta(
            max_gap if max_gap is not None else 2 * (dataset.native_step or DEFAULT_STEP)
        )
        self.chunk = pd.Timedelta(chunk)
        if self.max_gap < pd.Timedelta(0) or self.chunk <= pd.Timedelta(0):
            raise ValueError("max_gap must be nonnegative and chunk positive")

    def __iter__(self):
        """Read overlapping chunks once and sample NumPy arrays without per-row pandas lookup."""
        ticks = pd.DatetimeIndex(list(self.ticks))
        if not len(ticks):
            return
        ticks = pd.to_datetime(ticks, utc=True)
        seconds = interval_seconds(ticks, self.dataset.native_step or DEFAULT_STEP)
        if hasattr(self.ticks, "dt"):
            seconds = np.asarray([self.ticks.dt(t.to_pydatetime()) for t in ticks])
        offset = 0
        while offset < len(ticks):
            stop = max(offset + 1, ticks.searchsorted(ticks[offset] + self.chunk, side="left"))
            selected = ticks[offset:stop]
            end = selected[-1] + pd.Timedelta(seconds=float(seconds[stop - 1]))
            frame = self.dataset.read(selected[0] - self.max_gap, end, self.columns)
            times = frame.index.asi8
            values = frame.to_numpy()
            numeric = [pd.api.types.is_numeric_dtype(frame[c]) for c in self.columns]
            invalid = frame.isna().to_numpy()
            for column, is_numeric in enumerate(numeric):
                if is_numeric:
                    invalid[:, column] |= ~np.isfinite(
                        frame.iloc[:, column].to_numpy(dtype=float, na_value=np.nan)
                    )
                else:
                    invalid[:, column] |= (
                        frame.iloc[:, column]
                        .map(
                            lambda value: isinstance(value, (int, float, np.number))
                            and not np.isfinite(value)
                        )
                        .to_numpy(dtype=bool)
                    )
            column_names = np.asarray(self.columns, dtype=object)
            positions = np.searchsorted(times, selected.asi8, side="right") - 1
            for local, (t, previous) in enumerate(zip(selected, positions)):
                dt = float(seconds[offset + local])
                gap = previous < 0 or t.value - times[previous] > self.max_gap.value
                if self.align == "mean":
                    left = np.searchsorted(times, t.value, side="left")
                    right = np.searchsorted(times, t.value + round(dt * 1e9), side="left")
                    block = values[left:right]
                    raw = [
                        (
                            np.nanmean(block[:, i].astype(float))
                            if numeric[i] and np.isfinite(block[:, i].astype(float)).any()
                            else (block[-1, i] if len(block) else np.nan)
                        )
                        for i in range(len(self.columns))
                    ]
                    gap = not len(block)
                elif gap or (self.align == "exact" and times[previous] != t.value):
                    raw = [np.nan] * len(self.columns)
                    gap = True
                else:
                    raw = values[previous]
                row = dict(zip(self.columns, raw))
                if self.align != "mean":
                    missing = self.columns if gap else tuple(column_names[invalid[previous]])
                else:
                    missing = tuple(
                        k
                        for k, value in row.items()
                        if value is None
                        or pd.isna(value)
                        or isinstance(value, (int, float, np.number))
                        and not np.isfinite(value)
                    )
                yield Sample(t.to_pydatetime(), dt, row, missing, bool(gap))
            offset = stop
