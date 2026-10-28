"""Offline time-series input with explicit UTC timestamps and window selection."""

from pathlib import Path

import pandas as pd


class CSVTimeSeries:
    """Read the example CSV once and expose the same window interface as live drivers."""

    def __init__(self, path: str | Path):
        """Load semicolon-separated measurements indexed by UTC time."""
        self.frame = pd.read_csv(path, sep=";")
        self.frame.index = pd.to_datetime(self.frame.pop("Timestamp"), utc=True)
        self.frame = self.frame.sort_index()
        if self.frame.index.has_duplicates:
            raise ValueError("CSV timestamps must be unique")

    def latest(self, window):
        """Return the latest duration (Timedelta-compatible) or number of observations."""
        if isinstance(window, int):
            return self.frame.tail(window).copy()
        return self.frame.loc[self.frame.index[-1] - pd.Timedelta(window) :].copy()
