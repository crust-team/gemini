"""Validated time series for exogenous operating inputs, in SI units."""

from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, model_validator

from gemini.core.physics.units import to_si

# Input dimension and stored unit; conversion itself is owned by core.physics.units.
_UNITS = {
    "W": ("power", "W"),
    "kW": ("power", "W"),
    "MW": ("power", "W"),
    "K": ("temperature", "K"),
    "degC": ("temperature", "K"),
    "Pa": ("pressure", "Pa"),
    "bar": ("pressure", "Pa"),
    "barg": ("pressure", "Pa"),
    "kg/s": ("mass_flow", "kg/s"),
    "m3/s": ("volume_flow", "m3/s"),
    "m3/h": ("volume_flow", "m3/s"),
    "Hz": ("frequency", "Hz"),
    "J": ("energy", "J"),
    "kWh": ("energy", "J"),
    "currency/J": ("money_per_energy", "currency/J"),
    "currency/kWh": ("money_per_energy", "currency/J"),
    "-": ("dimensionless", "-"),
}


class Profile(BaseModel):
    """Strictly increasing UTC samples, evaluated as left-continuous step holds.

    `at(t)` uses the latest sample at or before t and holds the final sample.
    Queries before the first sample raise. Naive timestamps are interpreted as UTC.
    `sum` resampling sums sample values, not an integration over elapsed seconds.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    name: str
    quantity: str
    unit: str
    index: list[datetime]
    values: list[float]

    @model_validator(mode="after")
    def samples(self):
        """Normalise timestamps and reject empty, duplicate, unordered or nonfinite samples."""
        index = pd.to_datetime(self.index, utc=True)
        if not len(index) or len(index) != len(self.values):
            raise ValueError("Profile needs matching nonempty index and values")
        if not index.is_monotonic_increasing or not index.is_unique or index.hasnans:
            raise ValueError("Profile index must be strictly increasing")
        if not np.isfinite(self.values).all():
            raise ValueError("Profile values must be finite")
        self.index = index.to_pydatetime().tolist()
        return self

    @classmethod
    def from_csv(cls, path: str | Path, column, unit_in, time_column="Timestamp", tz=None):
        """Read comma/semicolon CSV, localise naive times and convert the selected column to SI."""
        if unit_in not in _UNITS:
            raise ValueError(f"Unsupported profile unit {unit_in!r}")
        frame = pd.read_csv(path, sep=None, engine="python")
        index = pd.DatetimeIndex(pd.to_datetime(frame[time_column]))
        if index.tz is None:
            index = index.tz_localize(tz or "UTC", ambiguous="raise", nonexistent="raise")
        quantity, unit = _UNITS[unit_in]
        return cls(
            name=column,
            quantity=quantity,
            unit=unit,
            index=index.to_pydatetime().tolist(),
            values=[to_si(v, unit_in) for v in frame[column]],
        )

    @classmethod
    def constant(cls, name, quantity, unit, value, start, periods, step: timedelta):
        """Construct a constant profile; value is already expressed in its declared SI unit."""
        if periods <= 0 or step.total_seconds() <= 0:
            raise ValueError("Profile periods and step must be positive")
        index = pd.date_range(start, periods=periods, freq=step)
        return cls(
            name=name,
            quantity=quantity,
            unit=unit,
            index=index.to_pydatetime().tolist(),
            values=[value] * periods,
        )

    def at(self, t: datetime) -> float:
        """Return the previous sample, raising before the profile starts."""
        target = pd.to_datetime(t, utc=True)
        position = pd.DatetimeIndex(self.index).searchsorted(target, side="right") - 1
        if position < 0:
            raise ValueError("Requested time precedes profile")
        return self.values[position]

    def resample(self, step: timedelta, how: Literal["mean", "sum", "first"]):
        """Aggregate in UTC left-closed bins; reject empty bins rather than filling them."""
        if step.total_seconds() <= 0 or how not in {"mean", "sum", "first"}:
            raise ValueError("Require a positive step and mean, sum or first")
        groups = self.to_series().resample(step)
        series = groups.sum(min_count=1) if how == "sum" else getattr(groups, how)()
        return type(self)(
            name=self.name,
            quantity=self.quantity,
            unit=self.unit,
            index=series.index.to_pydatetime().tolist(),
            values=series.tolist(),
        )

    def to_series(self) -> pd.Series:
        """Return an independent pandas series with a UTC DatetimeIndex."""
        return pd.Series(self.values, index=pd.DatetimeIndex(self.index), name=self.name)

    def __len__(self):
        """Return the number of samples."""
        return len(self.values)
