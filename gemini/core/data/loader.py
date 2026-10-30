"""Chunked time alignment of in-memory rows to finite ticks; it imports no engine code."""

from datetime import datetime, timedelta
from typing import NamedTuple

import numpy as np
import pandas as pd

from gemini.errors import DatasetError
from gemini.utils.time import DEFAULT_STEP, interval_seconds


class Sample(NamedTuple):
    """One row aligned to a tick; a stale hold or an empty mean bin is a row of NaN."""

    t: datetime
    dt: float
    row: dict


class Aligned(NamedTuple):
    """The samples of a whole run as arrays: ``times``, ``durations`` and one array per column."""

    times: list
    durations: np.ndarray
    columns: dict


class Loader:
    """Align raw rows to any finite tick iterable with bounded source reads.

    ``align="previous"`` holds the latest row at or before each tick, ``"exact"`` requires a
    row at the tick itself and ``"mean"`` averages numeric values over ``[tick, next_tick)``,
    keeping the last text value. A hold older than ``max_gap`` is a gap; by default
    ``max_gap`` is twice the dataset's native cadence (``DEFAULT_STEP`` for fewer than two
    rows). ``durations`` gives the seconds from each tick to the next; by default they are
    the tick spacing followed by the native cadence. The dataset is read one ``chunk`` of
    ticks at a time.
    """

    def __init__(
        self,
        dataset,
        ticks,
        columns=None,
        align="previous",
        max_gap=None,
        chunk=timedelta(days=7),
        durations=None,
    ):
        """Validate the alignment options; reading starts on iteration."""
        if align not in {"exact", "previous", "mean"}:
            raise DatasetError(f"Loader: align = {align!r}; expected 'exact', 'previous' or 'mean'")
        self.dataset, self.ticks, self.align = dataset, ticks, align
        self.columns = tuple(dataset.names if columns is None else columns)
        self.durations = durations
        self.max_gap = pd.Timedelta(
            max_gap if max_gap is not None else 2 * (dataset.native_step or DEFAULT_STEP)
        )
        self.chunk = pd.Timedelta(chunk)
        if self.max_gap < pd.Timedelta(0) or self.chunk <= pd.Timedelta(0):
            raise DatasetError(
                f"Loader: max_gap = {self.max_gap}, chunk = {self.chunk}; expected a "
                "nonnegative max_gap and a positive chunk"
            )

    def __iter__(self):
        """Read each chunk once and sample NumPy arrays without per-row pandas lookups."""
        sample = self._mean if self.align == "mean" else self._previous
        for frame, selected, seconds in self._frames():
            yield from sample(frame, selected, seconds)

    def arrays(self):
        """Return the same samples as ``Aligned`` arrays, without building a row per tick.

        ``previous`` and ``exact`` alignment are vectorised with the positions ``__iter__``
        uses; ``mean`` iterates and stacks the samples. Gaps are NaN, and a column array is
        ``float64`` unless the dataset holds text, when the arrays are ``object``.
        """
        if self.align == "mean":
            return self._stacked(list(self))
        times, durations, blocks = [], [], []
        for frame, selected, seconds in self._frames():
            held, gaps = self._hold(frame, selected)
            held[gaps] = np.nan
            blocks.append(held)
            times.extend(t.to_pydatetime() for t in selected)
            durations.append(np.asarray(seconds, dtype=float))
        if not blocks:
            return Aligned([], np.empty(0), {column: np.empty(0) for column in self.columns})
        values = np.concatenate(blocks)
        return Aligned(
            times, np.concatenate(durations), {c: values[:, i] for i, c in enumerate(self.columns)}
        )

    def _stacked(self, samples):
        """Stack iterated samples into ``Aligned`` arrays."""
        columns = {c: _column([sample.row[c] for sample in samples]) for c in self.columns}
        durations = np.array([sample.dt for sample in samples], dtype=float)
        return Aligned([sample.t for sample in samples], durations, columns)

    def _frames(self):
        """Yield ``(frame, ticks, seconds)`` for each chunk of ticks, reading it once."""
        ticks = pd.DatetimeIndex(list(self.ticks))
        if not len(ticks):
            return
        ticks = pd.to_datetime(ticks, utc=True).as_unit("ns")
        seconds = self.durations
        if seconds is None:
            seconds = interval_seconds(ticks, self.dataset.native_step or DEFAULT_STEP)
        for offset, stop in self._chunks(ticks):
            selected = ticks[offset:stop]
            end = selected[-1] + pd.Timedelta(seconds=float(seconds[stop - 1]))
            frame = self.dataset.read(selected[0] - self.max_gap, end, self.columns)
            yield frame, selected, seconds[offset:stop]

    def _chunks(self, ticks):
        """Yield ``(offset, stop)`` positions of consecutive tick chunks of at most ``chunk``."""
        offset = 0
        while offset < len(ticks):
            stop = max(offset + 1, ticks.searchsorted(ticks[offset] + self.chunk, side="left"))
            yield offset, stop
            offset = stop

    def _previous(self, frame, ticks, seconds):
        """Hold the latest row at or before each tick (``exact``: only a row at the tick).

        Row times are compared as nanosecond integers, the unit of ``Timestamp.value``, whatever
        the resolution of the dataset index (pandas 3 parses text as microseconds).
        """
        values = frame.to_numpy()
        positions, gaps = self._positions(frame, ticks)
        for t, previous, gap, dt in zip(ticks, positions, gaps, seconds):
            raw = [np.nan] * len(self.columns) if gap else values[previous]
            yield Sample(t.to_pydatetime(), float(dt), dict(zip(self.columns, raw)))

    def _positions(self, frame, ticks):
        """Return the held row position of each tick and whether the tick is a gap.

        A tick is a gap without a row at or before it, when the hold is older than ``max_gap``
        or, for ``exact`` alignment, when the row is not at the tick itself.
        """
        times = frame.index.as_unit("ns").asi8
        positions = np.searchsorted(times, ticks.asi8, side="right") - 1
        if not len(times):
            return positions, np.ones(len(ticks), dtype=bool)
        held = times[positions]
        gaps = (positions < 0) | (ticks.asi8 - held > self.max_gap.value)
        if self.align == "exact":
            gaps |= held != ticks.asi8
        return positions, gaps

    def _hold(self, frame, ticks):
        """Return the held rows as one 2D array (a copy) and the gap mask."""
        positions, gaps = self._positions(frame, ticks)
        values = frame.to_numpy()
        if values.dtype.kind in "iub":
            values = values.astype(float)
        if not len(values):
            return np.full((len(ticks), len(self.columns)), np.nan), gaps
        return values[positions], gaps

    def _mean(self, frame, ticks, seconds):
        """Average each numeric column over ``[tick, tick + dt)``; text keeps its last value."""
        times = frame.index.as_unit("ns").asi8
        values = frame.to_numpy()
        numeric = [pd.api.types.is_numeric_dtype(frame[column]) for column in self.columns]
        for t, dt in zip(ticks, seconds):
            dt = float(dt)
            left = np.searchsorted(times, t.value, side="left")
            right = np.searchsorted(times, t.value + round(dt * 1e9), side="left")
            block = values[left:right]
            raw = [_bin_value(block[:, i], is_numeric) for i, is_numeric in enumerate(numeric)]
            yield Sample(t.to_pydatetime(), dt, dict(zip(self.columns, raw)))


def _column(values):
    """Return ``values`` as a ``float64`` array, or as an ``object`` array when any is text."""
    array = np.array(values, dtype=object)
    try:
        return array.astype(float)
    except (TypeError, ValueError):
        return array


def _bin_value(column, is_numeric):
    """Return the mean of a numeric bin with finite values, else its last value or NaN."""
    if is_numeric and np.isfinite(column.astype(float)).any():
        return np.nanmean(column.astype(float))
    return column[-1] if len(column) else np.nan
