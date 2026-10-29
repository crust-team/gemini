"""Validated time series for exogenous operating inputs, in SI units."""

from datetime import datetime, timedelta
from typing import Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, PrivateAttr, model_validator

from gemini.core.physics import units
from gemini.errors import DatasetError, UnitError
from gemini.utils.time import to_utc_index

_QUANTITIES = {
    "W": "power",
    "K": "temperature",
    "Pa": "pressure",
    "kg/s": "mass_flow",
    "m3/s": "volume_flow",
    "Hz": "frequency",
    "J": "energy",
    "currency/J": "money_per_energy",
    "-": "dimensionless",
}
"""Quantity name recorded for each SI unit a profile may hold.

A raw profile unit is accepted when ``units`` converts it to one of these SI units.
"""


def _quantity_and_si_unit(unit):
    """Return the quantity name and SI unit of a supported raw profile unit."""
    si_unit = units.si_unit(unit)
    if si_unit not in _QUANTITIES:
        raise UnitError(f"Profile: unit = {unit!r}; expected a unit of {', '.join(_QUANTITIES)}")
    return _QUANTITIES[si_unit], si_unit


class Profile(BaseModel):
    """Strictly increasing UTC samples, evaluated with previous-sample zero-order holds.

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
    _times: pd.DatetimeIndex = PrivateAttr()

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
        self._times = pd.DatetimeIndex(self.index)
        return self

    @classmethod
    def from_series(cls, series, unit, tz="UTC"):
        """Convert an in-memory pandas Series in a supported raw unit to an SI profile."""
        quantity, si_unit = _quantity_and_si_unit(unit)
        index = to_utc_index(series.index, tz)
        return cls(
            name=series.name or "profile",
            quantity=quantity,
            unit=si_unit,
            index=index.to_pydatetime().tolist(),
            values=[units.to_si(value, unit) for value in series.to_numpy()],
        )

    @classmethod
    def constant(cls, value, *, unit, clock):
        """Build a constant profile on every tick of ``clock`` from a raw-unit value.

        Example: ``Profile.constant(150, unit="m3/h", clock=clock)``.
        """
        quantity, si_unit = _quantity_and_si_unit(unit)
        ticks = list(clock)
        return cls(
            name="constant",
            quantity=quantity,
            unit=si_unit,
            index=ticks,
            values=[units.to_si(value, unit)] * len(ticks),
        )

    def at(self, t: datetime) -> float:
        """Return the previous sample, raising before the profile starts."""
        target = pd.to_datetime(t, utc=True)
        position = self._times.searchsorted(target, side="right") - 1
        if position < 0:
            raise DatasetError(
                f"Profile {self.name}: time = {target}; expected a time at or after the "
                f"first sample {self._times[0]}"
            )
        return self.values[position]

    def resample(self, step: timedelta, how: Literal["mean", "sum", "first"]):
        """Aggregate in UTC left-closed bins; reject empty bins rather than filling them."""
        if step.total_seconds() <= 0 or how not in {"mean", "sum", "first"}:
            raise DatasetError(
                f"Profile.resample: step = {step}, how = {how!r}; expected a positive step and "
                "'mean', 'sum' or 'first'"
            )
        groups = self.to_series().resample(step)
        series = groups.sum(min_count=1) if how == "sum" else getattr(groups, how)()
        if series.isna().any():
            raise DatasetError(
                f"Profile {self.name}: resample bin at {series.index[series.isna()][0]} is "
                "empty; expected at least one sample in every bin"
            )
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
