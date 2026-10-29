"""Owned in-memory time-indexed data for engine runs."""

import hashlib
import json

import numpy as np
import pandas as pd

from gemini.core.types.bindings import ColumnInfo
from gemini.utils.time import median_step, to_utc


def _metadata(units):
    """Normalise string and mapping unit declarations."""
    return {
        name: ColumnInfo(unit=info) if isinstance(info, str) else ColumnInfo.model_validate(info)
        for name, info in (units or {}).items()
    }


class Dataset:
    """Time-indexed table of raw values held entirely in memory; units are metadata."""

    def __init__(self, frame, units=None):
        """Own and validate a sorted, unique, UTC-indexed frame."""
        if not isinstance(frame, pd.DataFrame):
            raise TypeError("Dataset requires a pandas DataFrame")
        self._frame = frame.copy().infer_objects()
        try:
            self._frame.index = pd.to_datetime(self._frame.index, utc=True)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Dataset timestamps are invalid: {exc}") from exc
        self._frame.index.name = "time"
        self._frame = self._frame.sort_index()
        if self._frame.index.has_duplicates or self._frame.index.hasnans:
            raise ValueError("Dataset timestamps must be sorted, unique and finite")
        if self._frame.columns.has_duplicates:
            raise ValueError("Dataset column names must be unique")
        if any(not isinstance(name, str) or not name for name in self._frame.columns):
            raise ValueError("Dataset column names must be nonempty strings")
        self.columns = _metadata(units)
        unknown = sorted(set(self.columns) - set(self._frame.columns))
        if unknown:
            raise ValueError("Unit metadata references unknown columns: " + ", ".join(unknown))
        self.names = tuple(self._frame.columns)

    @property
    def frame(self):
        """Return the owned frame for compatibility with read-only analysis code."""
        return self._frame

    @property
    def start(self):
        """Return the first UTC timestamp, or None for an empty dataset."""
        return self._frame.index[0].to_pydatetime() if len(self) else None

    @property
    def end(self):
        """Return the final UTC timestamp, or None for an empty dataset."""
        return self._frame.index[-1].to_pydatetime() if len(self) else None

    @property
    def native_step(self):
        """Return median timestamp spacing, or None when fewer than two rows exist."""
        if len(self) < 2:
            return None
        return median_step(self._frame.index).to_pytimedelta()

    def read(self, start=None, end=None, columns=None):
        """Return an independent inclusive UTC window and optional column subset."""
        selected = list(columns) if columns is not None else list(self.names)
        missing = sorted(set(selected) - set(self.names))
        if missing:
            raise ValueError("Dataset is missing columns: " + ", ".join(missing))
        lower = to_utc(start) if start is not None else None
        upper = to_utc(end) if end is not None else None
        if lower is not None and upper is not None and lower > upper:
            return self._frame.iloc[:0].loc[:, selected].copy()
        return self._frame.loc[lower:upper, selected].copy()

    def window(self, start=None, end=None):
        """Return an owned inclusive subset."""
        return type(self)(self.read(start, end), self.columns)

    def after(self, t):
        """Return rows strictly after a timestamp."""
        if t is None:
            return type(self)(self._frame, self.columns)
        frame = self._frame.loc[self._frame.index > pd.Timestamp(to_utc(t))]
        return type(self)(frame, self.columns)

    def __len__(self):
        """Return the observation count."""
        return len(self._frame)

    def fingerprint(self):
        """Return a stable hash of index, values, dtypes and unit metadata."""
        digest = hashlib.sha256()
        digest.update(pd.util.hash_pandas_object(self._frame, index=True).values.tobytes())
        descriptor = {
            "columns": list(self._frame.columns),
            "dtypes": [str(dtype) for dtype in self._frame.dtypes],
            "units": {
                name: info.model_dump(mode="json") for name, info in sorted(self.columns.items())
            },
        }
        digest.update(json.dumps(descriptor, sort_keys=True, separators=(",", ":")).encode())
        return digest.hexdigest()

    def to_frame(self):
        """Return an independent copy of the complete table."""
        return self._frame.copy()

    def describe(self):
        """Return lossless JSON-compatible in-memory samples for checkpoints."""
        return {
            "kind": "memory",
            "columns": list(self._frame.columns),
            "index": [value.isoformat() for value in self._frame.index],
            "data": self._frame.astype(object).where(self._frame.notna(), None).values.tolist(),
            "dtypes": {name: str(dtype) for name, dtype in self._frame.dtypes.items()},
            "units": {name: info.model_dump(mode="json") for name, info in self.columns.items()},
        }

    @staticmethod
    def reopen(description):
        """Rebuild an in-memory dataset descriptor saved in a checkpoint."""
        if description.get("kind") != "memory":
            raise ValueError(f"Unknown in-memory dataset kind {description.get('kind')!r}")
        frame = pd.DataFrame(
            description["data"],
            columns=description["columns"],
            index=pd.to_datetime(description["index"], utc=True),
        )
        for name, dtype in description.get("dtypes", {}).items():
            frame[name] = frame[name].astype(dtype)
        return Dataset(frame, description.get("units"))

    @staticmethod
    def from_frame(df, time_column=None, units=None, tz="UTC"):
        """Build from a frame, using a named time column or its DatetimeIndex."""
        frame = df.copy()
        if time_column is not None:
            if time_column not in frame:
                raise ValueError(f"Dataset time column {time_column!r} is missing")
            index = pd.DatetimeIndex(pd.to_datetime(frame.pop(time_column), format="mixed"))
        else:
            if not isinstance(frame.index, pd.DatetimeIndex):
                raise TypeError(
                    "Dataset.from_frame requires a DatetimeIndex when time_column is omitted"
                )
            index = pd.DatetimeIndex(frame.index)
        if index.tz is None:
            index = index.tz_localize(tz, ambiguous="raise", nonexistent="raise")
        frame.index = index.tz_convert("UTC")
        return Dataset(frame, units)

    @staticmethod
    def from_dict(data, time, units=None, tz="UTC"):
        """Build from column-oriented lists or NumPy arrays and a separate time axis."""
        return Dataset.from_frame(pd.DataFrame(data, index=time), units=units, tz=tz)

    @staticmethod
    def from_records(rows, time_column, units=None, tz="UTC"):
        """Build from row dictionaries containing a named timestamp field."""
        return Dataset.from_frame(pd.DataFrame.from_records(rows), time_column, units, tz)

    @staticmethod
    def from_numpy(time, values, columns, units=None, tz="UTC"):
        """Build from a two-dimensional value array and explicit column names."""
        values = np.asarray(values)
        if values.ndim != 2 or values.shape[1] != len(columns):
            raise ValueError("values must be 2D with one column per supplied name")
        frame = pd.DataFrame(values, index=time, columns=columns)
        return Dataset.from_frame(frame, units=units, tz=tz)

    @staticmethod
    def from_profiles(profiles):
        """Combine profiles sharing one clock; their values and units are already SI."""
        if not profiles:
            raise ValueError("Profiles must not be empty")
        index = next(iter(profiles.values())).index
        if any(profile.index != index for profile in profiles.values()):
            raise ValueError("Profiles must share the same index; resample explicitly")
        frame = pd.DataFrame(
            {name: profile.values for name, profile in profiles.items()}, index=index
        )
        units = {
            name: ColumnInfo(unit=profile.unit, quantity=profile.quantity)
            for name, profile in profiles.items()
        }
        return Dataset(frame, units)
