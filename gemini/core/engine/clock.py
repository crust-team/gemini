"""Finite UTC clocks owned by the execution engine."""

from abc import ABC

import pandas as pd

from gemini.utils.time import DEFAULT_STEP, interval_seconds, median_step, parse_duration, to_utc


class Clock(ABC):
    """Finite ordered ticks; dt is elapsed seconds to the next tick, including a final step."""

    def __init__(self, ticks, step=None):
        """Validate ordered unique UTC ticks and retain a final interval."""
        self.ticks = pd.DatetimeIndex(pd.to_datetime(list(ticks), utc=True))
        if not self.ticks.is_unique or not self.ticks.is_monotonic_increasing or self.ticks.hasnans:
            raise ValueError("Clock ticks must be strictly increasing and finite")
        inferred = median_step(self.ticks) or DEFAULT_STEP
        self.step = parse_duration(step if step is not None else inferred)
        self._durations = interval_seconds(self.ticks, self.step)

    def __iter__(self):
        """Iterate UTC datetimes without sleeping or scheduling."""
        return iter(self.ticks.to_pydatetime())

    def __len__(self):
        """Return the finite tick count."""
        return len(self.ticks)

    def position(self, t):
        """Return the exact tick position; reject timestamps outside this clock."""
        return int(self.ticks.get_loc(pd.Timestamp(to_utc(t))))

    def dt(self, t):
        """Return seconds to the next tick, using the declared step for the final tick."""
        return float(self._durations[self.position(t)])

    def after(self, t):
        """Return strictly subsequent ticks, retaining the original final-step duration."""
        return Clock(self.ticks[self.ticks > pd.Timestamp(to_utc(t))], self.step)

    def describe(self):
        """Return full irregular ticks or a compact fixed-range descriptor."""
        return dict(kind="ticks", ticks=[t.isoformat() for t in self.ticks], step=str(self.step))

    @staticmethod
    def reopen(spec):
        """Restore the precise finite tick schedule from a checkpoint."""
        if spec["kind"] == "fixed":
            return FixedClock(spec["start"], spec["end"], spec["step"])
        return Clock(spec["ticks"], spec["step"])

    @staticmethod
    def year(year, step="1h", tz="UTC"):
        """Cover one calendar year in the chosen timezone, excluding the next year's start."""
        start = pd.Timestamp(year=year, month=1, day=1, tz=tz)
        end = pd.Timestamp(year=year + 1, month=1, day=1, tz=tz)
        ticks = pd.date_range(start, end, freq=parse_duration(step), inclusive="left")
        return FixedClock(ticks[0], ticks[-1], step)

    @staticmethod
    def days(year, month, day, days=1, step="1h", tz="UTC"):
        """Cover calendar days in the chosen timezone; DST days may have 23 or 25 hours."""
        if days <= 0:
            raise ValueError("days must be positive")
        start = pd.Timestamp(year=year, month=month, day=day, tz=tz)
        end = start + pd.DateOffset(days=days)
        ticks = pd.date_range(start, end, freq=parse_duration(step), inclusive="left")
        return FixedClock(ticks[0], ticks[-1], step)

    @staticmethod
    def range(start, end, step):
        """Construct an inclusive fixed grid over datetime or ISO-string bounds."""
        return FixedClock(start, end, step)

    @staticmethod
    def from_data(dataset, step=None):
        """Use actual observation times, or a regular grid over the source range."""
        return DataClock(dataset, step)


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


class DataClock(Clock):
    """Observation timestamps, or an explicitly requested regular sampling grid."""

    def __init__(self, dataset, step=None):
        """Discover timestamps without requesting data columns when cadence is irregular."""
        if dataset.start is None or dataset.end is None:
            ticks = []
        elif step is None:
            ticks = dataset.read(dataset.start, dataset.end, columns=[]).index
        else:
            ticks = pd.date_range(dataset.start, dataset.end, freq=parse_duration(step))
        super().__init__(ticks, step or dataset.native_step)


class LiveClock(Clock):
    """A finite (last_processed, now] window, anchored to the source's starting time."""

    def __init__(self, last_processed, now, step, start=None):
        """Select only new completed ticks; never sleep or infer a scheduler."""
        step = parse_duration(step)
        anchor = to_utc(start) if start is not None else to_utc(last_processed or now)
        ticks = pd.date_range(anchor, to_utc(now), freq=step)
        if last_processed is not None:
            ticks = ticks[ticks > pd.Timestamp(to_utc(last_processed))]
        super().__init__(ticks, step)
