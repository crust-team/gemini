"""Owned in-memory time-indexed data for engine runs."""

import hashlib
import json

import numpy as np
import pandas as pd

from gemini._utils.strings import did_you_mean, join_names
from gemini._utils.time import median_step, to_utc, to_utc_index
from gemini.errors import RunError
from gemini.types.bindings import ColumnInfo


def _metadata(units):
    """Normalise string and mapping unit declarations."""
    return {
        name: ColumnInfo(unit=info) if isinstance(info, str) else ColumnInfo.model_validate(info)
        for name, info in (units or {}).items()
    }


def _first_invalid_timestamp(index):
    """Return the first NaT or repeated timestamp of a sorted index."""
    if index.hasnans:
        return "NaT"
    return index[index.duplicated()][0].isoformat()


class Dataset:
    """Time-indexed table of raw values held entirely in memory; units are metadata."""

    def __init__(self, frame, units=None):
        """Own and validate a sorted, unique, UTC-indexed frame."""
        if not isinstance(frame, pd.DataFrame):
            raise RunError(
                f"Dataset: frame = {type(frame).__name__}; expected a pandas DataFrame",
                code="invalid_data",
            )
        self._frame = frame.copy().infer_objects()
        try:
            self._frame.index = pd.to_datetime(self._frame.index, utc=True)
        except (TypeError, ValueError) as exc:
            raise RunError(
                f"Dataset: index is invalid; expected timestamps ({exc})", code="invalid_data"
            ) from exc
        self._frame.index.name = "time"
        self._frame = self._frame.sort_index()
        if self._frame.index.has_duplicates or self._frame.index.hasnans:
            raise RunError(
                f"Dataset: timestamp = {_first_invalid_timestamp(self._frame.index)}; expected "
                "unique timestamps and no NaT",
                code="invalid_data",
            )
        self._check_column_names()
        self.columns = _metadata(units)
        unknown = sorted(set(self.columns) - set(self._frame.columns))
        if unknown:
            raise RunError(
                f"Dataset: unit metadata columns = {join_names(unknown)}; expected data "
                f"columns{did_you_mean(unknown[0], self._frame.columns)}",
                code="invalid_data",
            )
        self.names = tuple(self._frame.columns)

    def _check_column_names(self):
        """Reject repeated, empty or non-string column names."""
        columns = self._frame.columns
        if columns.has_duplicates:
            repeated = sorted(set(columns[columns.duplicated()]))
            raise RunError(
                f"Dataset: column names = {repeated}; expected unique names", code="invalid_data"
            )
        invalid = [name for name in columns if not isinstance(name, str) or not name]
        if invalid:
            raise RunError(
                f"Dataset: column names = {invalid!r}; expected nonempty strings",
                code="invalid_data",
            )

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

    def unit(self, column, default):
        """Return the unit recorded for ``column``, or ``default`` when it has no metadata."""
        info = self.columns.get(column)
        return info.unit if info is not None else default

    def read(self, start=None, end=None, columns=None):
        """Return an independent inclusive UTC window and optional column subset."""
        selected = list(columns) if columns is not None else list(self.names)
        missing = sorted(set(selected) - set(self.names))
        if missing:
            raise RunError(
                f"Dataset: columns = {join_names(missing)}; expected columns of this dataset"
                f"{did_you_mean(missing[0], self.names)}",
                code="invalid_data",
            )
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
        """Return a stable hash of index, values, dtypes and unit metadata.

        Checkpoints store it for information only; nothing compares it when a run resumes.
        """
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

    @staticmethod
    def from_frame(df, time_column=None, units=None, tz="UTC"):
        """Build from a frame, using a named time column or its DatetimeIndex."""
        frame = df.copy()
        if time_column is not None:
            if time_column not in frame:
                raise RunError(
                    f"Dataset.from_frame: time_column = {time_column!r}; expected one of "
                    f"{join_names(map(str, frame.columns))}{did_you_mean(time_column, frame)}",
                    code="invalid_data",
                )
            times = frame.pop(time_column)
        elif isinstance(frame.index, pd.DatetimeIndex):
            times = frame.index
        else:
            raise RunError(
                f"Dataset.from_frame: index = {type(frame.index).__name__}; expected a "
                "DatetimeIndex when time_column is omitted",
                code="invalid_data",
            )
        frame.index = to_utc_index(times, tz)
        return Dataset(frame, units)

    @staticmethod
    def from_dict(data, time, units=None, tz="UTC"):
        """Build from column-oriented lists or NumPy arrays and a separate time axis."""
        return Dataset.from_frame(
            pd.DataFrame(data, index=to_utc_index(time, tz)), units=units, tz=tz
        )

    @staticmethod
    def from_records(rows, time_column, units=None, tz="UTC"):
        """Build from row dictionaries containing a named timestamp field."""
        return Dataset.from_frame(pd.DataFrame.from_records(rows), time_column, units, tz)

    @staticmethod
    def from_numpy(time, values, columns, units=None, tz="UTC"):
        """Build from a two-dimensional value array and explicit column names."""
        values = np.asarray(values)
        if values.ndim != 2 or values.shape[1] != len(columns):
            raise RunError(
                f"Dataset.from_numpy: values shape = {values.shape}; expected (rows, "
                f"{len(columns)}) for {len(columns)} column names",
                code="invalid_data",
            )
        frame = pd.DataFrame(values, index=to_utc_index(time, tz), columns=columns)
        return Dataset.from_frame(frame, units=units, tz=tz)

    @staticmethod
    def from_profiles(profiles):
        """Combine profiles sharing one clock; their values and units are already SI."""
        if not profiles:
            raise RunError(
                "Dataset.from_profiles: profiles = {}; expected at least one", code="invalid_data"
            )
        index = next(iter(profiles.values())).index
        differing = [name for name, profile in profiles.items() if profile.index != index]
        if differing:
            raise RunError(
                f"Dataset.from_profiles: profile {differing[0]!r} index differs from the first "
                "profile; expected one shared index (resample explicitly)",
                code="invalid_data",
            )
        frame = pd.DataFrame(
            {name: profile.values for name, profile in profiles.items()}, index=index
        )
        units = {
            name: ColumnInfo(unit=profile.unit, quantity=profile.quantity)
            for name, profile in profiles.items()
        }
        return Dataset(frame, units)


def as_dataset(data):
    """Return the run input as a ``Dataset``: a ``Dataset`` as it is, a DataFrame wrapped.

    A DataFrame needs a timezone-aware ``DatetimeIndex`` (any zone; the instants become UTC) and
    columns named by the binding ``column``. Its values have the units of the bindings, or those
    a frame states in ``attrs["units"]``, as a ``gm.schedule`` plan does. A naive
    index raises ``RunError``, because a local time without a zone is ambiguous.
    """
    if isinstance(data, Dataset):
        return data
    if not isinstance(data, pd.DataFrame):
        raise RunError(
            f"run input: type = {type(data).__name__}; expected a Dataset or a pandas DataFrame",
            code="invalid_data",
        )
    index = data.index
    if not isinstance(index, pd.DatetimeIndex) or index.tz is None:
        raise RunError(
            f"run input: index = {type(index).__name__} without a timezone; expected a "
            "timezone-aware DatetimeIndex (UTC)",
            code="invalid_data",
        )
    stated = data.attrs.get("units", {})
    return Dataset(data, {name: unit for name, unit in stated.items() if name in data})


def bound_unit(dataset, binding):
    """Return the unit of a bound column: the dataset's metadata beats the binding's own unit."""
    return dataset.unit(binding.column, binding.unit)
