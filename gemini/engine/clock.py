"""Finite UTC clocks owned by the execution engine."""

import numpy as np
import pandas as pd

from gemini.errors import CheckpointError, ClockError
from gemini.utils.time import DEFAULT_STEP, interval_seconds, median_step, parse_duration, to_utc


def _first_unordered(ticks):
    """Return the first tick that is NaT, repeated or earlier than its predecessor."""
    if ticks.hasnans:
        return "NaT"
    position = int(np.flatnonzero(np.diff(ticks.asi8) <= 0)[0]) + 1
    return ticks[position].isoformat()


class Clock:
    """Finite ordered ticks; dt is elapsed seconds to the next tick, including a final step.

    Without an explicit ``step`` the final interval is the median tick spacing, or
    ``DEFAULT_STEP`` (one hour) when fewer than two ticks give no spacing.
    """

    def __init__(self, ticks, step=None):
        """Validate ordered unique UTC ticks and retain a final interval."""
        self.ticks = pd.DatetimeIndex(pd.to_datetime(list(ticks), utc=True))
        if not self.ticks.is_unique or not self.ticks.is_monotonic_increasing or self.ticks.hasnans:
            raise ClockError(
                f"Clock: tick = {_first_unordered(self.ticks)}; expected strictly increasing "
                "timestamps"
            )
        inferred = median_step(self.ticks) or DEFAULT_STEP
        self.step = parse_duration(step if step is not None else inferred)
        self._durations = interval_seconds(self.ticks, self.step)

    def __iter__(self):
        """Iterate UTC datetimes without sleeping or scheduling."""
        return iter(self.ticks.to_pydatetime())

    def __len__(self):
        """Return the finite tick count."""
        return len(self.ticks)

    @property
    def durations(self):
        """Return seconds from each tick to the next, with the final step after the last."""
        return self._durations.copy()

    def position(self, t):
        """Return the exact tick position; reject timestamps outside this clock."""
        timestamp = pd.Timestamp(to_utc(t))
        if timestamp not in self.ticks:
            span = (
                f"{self.ticks[0].isoformat()} .. {self.ticks[-1].isoformat()}" if len(self) else ""
            )
            raise ClockError(
                f"Clock: t = {timestamp.isoformat()}; expected one of {len(self)} ticks {span}"
            )
        return int(self.ticks.get_loc(timestamp))

    def dt(self, t):
        """Return seconds to the next tick, using the declared step for the final tick."""
        return float(self._durations[self.position(t)])

    def after(self, t):
        """Return strictly subsequent ticks, retaining the original final-step duration."""
        return Clock(self.ticks[self.ticks > pd.Timestamp(to_utc(t))], self.step)

    def window(self, start=None, end=None):
        """Return the ticks within inclusive optional bounds, retaining the final step."""
        selected = self.ticks
        if start is not None:
            selected = selected[selected >= pd.Timestamp(to_utc(start))]
        if end is not None:
            selected = selected[selected <= pd.Timestamp(to_utc(end))]
        return Clock(selected, self.step)

    def describe(self):
        """Return full irregular ticks or a compact fixed-range descriptor."""
        return dict(kind="ticks", ticks=[t.isoformat() for t in self.ticks], step=str(self.step))

    @staticmethod
    def reopen(spec):
        """Restore the precise finite tick schedule from a checkpoint."""
        if spec.get("kind") == "fixed":
            return FixedClock(spec["start"], spec["end"], spec["step"])
        if spec.get("kind") == "ticks":
            return Clock(spec["ticks"], spec["step"])
        raise CheckpointError(f"Clock: kind = {spec.get('kind')!r}; expected 'fixed' or 'ticks'")

    @staticmethod
    def year(year, step="1h", tz="UTC"):
        """Cover one calendar year in the chosen timezone, excluding the next year's start."""
        start = pd.Timestamp(year=year, month=1, day=1, tz=tz)
        end = pd.Timestamp(year=year + 1, month=1, day=1, tz=tz)
        return Clock._calendar(start, end, step)

    @staticmethod
    def days(year, month, day, days=1, step="1h", tz="UTC"):
        """Cover calendar days in the chosen timezone; DST days may have 23 or 25 hours."""
        if days <= 0:
            raise ClockError(f"Clock.days: days = {days!r}; expected a positive count")
        start = pd.Timestamp(year=year, month=month, day=day, tz=tz)
        return Clock._calendar(start, start + pd.DateOffset(days=days), step)

    @staticmethod
    def _calendar(start, end, step):
        """Return the local calendar ticks in ``[start, end)``.

        A daily step follows local midnight, so in a DST zone the ticks are not a fixed UTC
        grid. A whole number of days is passed as calendar ``Day`` offsets because pandas 3 reads
        a ``Timedelta`` frequency as a fixed 24 hours. The compact ``FixedClock`` is used only
        when it reproduces the ticks exactly.
        """
        frequency = parse_duration(step)
        days, remainder = divmod(frequency, pd.Timedelta(days=1))
        if days and not remainder:
            frequency = pd.offsets.Day(days)
        ticks = pd.date_range(start, end, freq=frequency, inclusive="left")
        grid = FixedClock(ticks[0], ticks[-1], step)
        if grid.ticks.equals(ticks.tz_convert("UTC")):
            return grid
        return Clock(ticks, step)

    @staticmethod
    def range(start, end, step):
        """Construct an inclusive fixed grid over datetime or ISO-string bounds."""
        return FixedClock(start, end, step)

    @staticmethod
    def from_data(dataset, step=None):
        """Use actual observation times, or a regular grid over the source range.

        Observation times are read without data columns, so irregular cadence costs no reads.
        """
        if not len(dataset):
            return Clock([], step or dataset.native_step)
        if step is None:
            ticks = dataset.read(dataset.start, dataset.end, columns=[]).index
        else:
            ticks = pd.date_range(dataset.start, dataset.end, freq=parse_duration(step))
        return Clock(ticks, step or dataset.native_step)


class FixedClock(Clock):
    """A fixed positive cadence over inclusive bounds."""

    def __init__(self, start, end, step):
        """Convert bounds to UTC before building the grid."""
        super().__init__(pd.date_range(to_utc(start), to_utc(end), freq=parse_duration(step)), step)

    def describe(self):
        """Store regular ranges compactly; preserve empty schedules explicitly."""
        if not len(self):
            return super().describe()
        return dict(
            kind="fixed",
            start=self.ticks[0].isoformat(),
            end=self.ticks[-1].isoformat(),
            step=str(self.step),
        )
