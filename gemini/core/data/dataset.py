"""Time-indexed raw data; physical units stay metadata until engine boundaries."""

from abc import ABC, abstractmethod
from pathlib import Path

import numpy as np
import pandas as pd

from gemini.core.types.bindings import ColumnInfo, utc


def _metadata(units):
    return {
        name: ColumnInfo(unit=info) if isinstance(info, str) else ColumnInfo.model_validate(info)
        for name, info in (units or {}).items()
    }


class Dataset(ABC):
    """A finite, UTC-indexed source with inclusive reads and reproducible descriptions."""

    @abstractmethod
    def read(self, start, end, columns=None):
        """Read raw values in the inclusive UTC interval."""

    @property
    @abstractmethod
    def start(self):
        """Return the earliest available timestamp, or None for an empty source."""

    @property
    @abstractmethod
    def end(self):
        """Return the latest available timestamp, or None for an empty source."""

    @property
    @abstractmethod
    def native_step(self):
        """Return median timestamp spacing when known."""

    @abstractmethod
    def __len__(self):
        """Count available rows."""

    @abstractmethod
    def describe(self):
        """Describe how to reopen this source, never including credentials."""

    def window(self, start=None, end=None):
        """Return a bounded view without copying or reading the entire source."""
        return WindowDataset(self, start, end)

    @staticmethod
    def from_csv(path, time_column="Timestamp", sep=None, tz="UTC", units=None):
        """Read CSV with delimiter detection, preserving text flags and localising naive times."""
        path = Path(path).resolve()
        frame = pd.read_csv(path, sep=sep, **({"engine": "python"} if sep is None else {}))
        index = pd.DatetimeIndex(pd.to_datetime(frame.pop(time_column), format="mixed"))
        frame.index = index.tz_localize(tz) if index.tz is None else index
        source = dict(kind="csv", path=str(path), time_column=time_column, sep=sep, tz=tz)
        return FrameDataset(frame, units, source)

    @staticmethod
    def from_frame(df, units=None):
        """Copy a timestamp-indexed frame; naive timestamps are UTC."""
        return FrameDataset(df, units)

    @staticmethod
    def from_profiles(profiles):
        """Combine aligned SI profiles and retain their declared physical units."""
        return ProfileDataset(profiles)

    @staticmethod
    def from_csv_driver(project_folder):
        """Wrap the existing CSV driver; refresh on reads so periodic live calls see new rows."""
        from gemini.core.data.drivers.csv_driver import CSVDriver

        folder = Path(project_folder).resolve()
        paths = sorted(folder.glob("*_dataset.csv")) if folder.is_dir() else [folder]
        if len(paths) != 1:
            raise ValueError(f"{folder}: expected one *_dataset.csv, found {len(paths)}")
        driver = CSVDriver()
        driver.update_parameters({"url": str(paths[0])})
        return DriverDataset(driver, dict(kind="csv_driver", project_folder=str(folder)))

    @staticmethod
    def from_influx(url, token, org, bucket, tags):
        """Connect to InfluxDB; token names an environment variable, tags select plant and asset."""
        from gemini.core.data.drivers.sources import InfluxSource

        source = dict(kind="influx", url=url, token=token, org=org, bucket=bucket, tags=tags)
        return DriverDataset(
            InfluxSource(**{k: v for k, v in source.items() if k != "kind"}), source
        )

    @staticmethod
    def from_aveva(parameters, streams, start, end, step="15min", secret_env="AVEVA_CLIENT_SECRET"):
        """Read named AVEVA streams over a bounded range with an environment-provided secret."""
        from gemini.core.data.drivers.sources import AvevaSource

        if any(k in parameters for k in ("client_secret", "password", "token")):
            raise ValueError("Pass secret_env, not credentials in parameters")
        source = dict(
            kind="aveva",
            parameters=parameters,
            streams=streams,
            start=utc(start).isoformat(),
            end=utc(end).isoformat(),
            step=str(pd.Timedelta(step)),
            secret_env=secret_env,
        )
        return DriverDataset(
            AvevaSource(**{k: v for k, v in source.items() if k != "kind"}), source
        )

    @staticmethod
    def reopen(description):
        """Restore a saved source descriptor, including inline in-memory datasets."""
        spec = dict(description)
        kind = spec.pop("kind")
        units = spec.pop("units", {})
        if kind == "window":
            return Dataset.reopen(spec["source"]).window(spec["start"], spec["end"])
        if kind == "frame":
            frame = pd.DataFrame(
                spec["data"], columns=spec["columns"], index=pd.to_datetime(spec["index"], utc=True)
            )
            for name, dtype in spec["dtypes"].items():
                frame[name] = frame[name].astype(dtype)
            return FrameDataset(frame, units)
        constructors = {
            "csv": Dataset.from_csv,
            "csv_driver": Dataset.from_csv_driver,
            "influx": Dataset.from_influx,
            "aveva": Dataset.from_aveva,
        }
        if kind not in constructors:
            raise ValueError(f"Unknown dataset kind {kind!r}")
        dataset = constructors[kind](**spec)
        dataset.columns.update(_metadata(units))
        return dataset


class FrameDataset(Dataset):
    """An owned, sorted frame; descriptions embed in-memory samples at full float precision."""

    def __init__(self, frame, units=None, source=None):
        """Validate unique timestamps, preserving column values and optional reopen information."""
        self.frame = frame.copy()
        self.frame.index = pd.to_datetime(self.frame.index, utc=True)
        self.frame.index.name = "timestamp"
        self.frame = self.frame.sort_index()
        if self.frame.index.has_duplicates or self.frame.index.hasnans:
            raise ValueError("Dataset timestamps must be unique and finite")
        if self.frame.columns.has_duplicates:
            raise ValueError("Dataset column names must be unique")
        self.columns = _metadata(units)
        self.names = tuple(self.frame.columns)
        self._source = source

    @property
    def start(self):
        """Return the first UTC timestamp, or None."""
        return self.frame.index[0].to_pydatetime() if len(self) else None

    @property
    def end(self):
        """Return the last UTC timestamp, or None."""
        return self.frame.index[-1].to_pydatetime() if len(self) else None

    @property
    def native_step(self):
        """Return median spacing, without inventing a cadence for a single row."""
        if len(self) < 2:
            return None
        return pd.Timedelta(
            int(np.median(np.diff(self.frame.index.asi8))), unit="ns"
        ).to_pytimedelta()

    def read(self, start, end, columns=None):
        """Return an independent inclusive window and optional column selection."""
        frame = self.frame.loc[
            utc(start) if start is not None else None : utc(end) if end is not None else None
        ]
        return frame.loc[:, list(columns) if columns is not None else slice(None)].copy()

    def __len__(self):
        """Return the number of observations."""
        return len(self.frame)

    def describe(self):
        """Return a file reference or lossless JSON-compatible inline observations."""
        spec = self._source or dict(
            kind="frame",
            columns=list(self.frame.columns),
            index=[t.isoformat() for t in self.frame.index],
            data=self.frame.astype(object).where(self.frame.notna(), None).values.tolist(),
            dtypes={k: str(v) for k, v in self.frame.dtypes.items()},
        )
        return dict(spec, units={k: v.model_dump() for k, v in self.columns.items()})


class ProfileDataset(FrameDataset):
    """Aligned profiles; values are already SI, preventing accidental double conversion."""

    def __init__(self, profiles):
        """Reject differing time grids; resampling is always an explicit caller choice."""
        if not profiles:
            raise ValueError("Profiles must not be empty")
        index = next(iter(profiles.values())).index
        if any(p.index != index for p in profiles.values()):
            raise ValueError("Profiles must share the same index; resample explicitly")
        super().__init__(
            pd.DataFrame({k: p.values for k, p in profiles.items()}, index=index),
            {k: ColumnInfo(unit=p.unit, quantity=p.quantity) for k, p in profiles.items()},
        )


class DriverDataset(Dataset):
    """Adapt existing database drivers to bounded reads and reopenable metadata."""

    def __init__(self, driver, source):
        """Connect lazily through driver metadata; credentials remain outside descriptions."""
        self.driver, self._source = driver, source
        self.columns = {}
        self._file_version = None
        if not hasattr(driver, "df"):
            driver.connect()
        self._refresh()

    def _refresh(self):
        if hasattr(self.driver, "df"):
            stat = Path(self.driver.parameters["url"]).stat()
            version = (stat.st_mtime_ns, stat.st_size)
            if version == self._file_version:
                return
            self.driver.connect()
            self._file_version = version
            self._frame = FrameDataset(self.driver.df)
            self.names = self._frame.names
        else:
            self.names = tuple(self.driver.names)

    @property
    def start(self):
        """Return the first source observation."""
        return self._frame.start if hasattr(self, "_frame") else self.driver.start

    @property
    def end(self):
        """Return the latest observed source time."""
        return self.latest_time()

    def latest_time(self):
        """Refresh the source bounds for an externally scheduled live call."""
        self._refresh()
        return self._frame.end if hasattr(self, "_frame") else self.driver.end

    @property
    def native_step(self):
        """Return the CSV's median cadence or the remote driver's declared cadence."""
        return self._frame.native_step if hasattr(self, "_frame") else self.driver.native_step

    def read(self, start, end, columns=None):
        """Read an inclusive range, preserving numeric values and text status flags."""
        if hasattr(self, "_frame"):
            self._refresh()
            return self._frame.read(start, end, columns)
        return self.driver.read(start, end, columns)

    def __len__(self):
        """Count observations in the current source range."""
        if hasattr(self, "_frame"):
            return len(self._frame)
        return len(self.read(self.start, self.end))

    def describe(self):
        """Return connection options containing environment names, never secret values."""
        return dict(self._source, units={k: v.model_dump() for k, v in self.columns.items()})


class WindowDataset(Dataset):
    """A finite view retaining the original source and its reopening information."""

    def __init__(self, source, start, end):
        """Intersect requested bounds with the parent source."""
        self.source = source
        self._start = (
            max(utc(start), source.start) if start is not None and source.start else source.start
        )
        self._end = min(utc(end), source.end) if end is not None and source.end else source.end
        self.columns, self.names = source.columns, source.names

    @property
    def start(self):
        """Return the lower inclusive bound."""
        return self._start

    @property
    def end(self):
        """Return the upper inclusive bound."""
        return self._end

    @property
    def native_step(self):
        """Retain source cadence even when the window has fewer than two rows."""
        return self.source.native_step

    def read(self, start, end, columns=None):
        """Intersect the requested interval with this view."""
        return self.source.read(
            max(utc(start), self.start) if start else self.start,
            min(utc(end), self.end) if end else self.end,
            columns,
        )

    def __len__(self):
        """Count observations inside the bounds."""
        return len(self.read(self.start, self.end))

    def describe(self):
        """Retain both the reopenable parent and inclusive bounds."""
        return dict(
            kind="window",
            source=self.source.describe(),
            start=self.start.isoformat() if self.start else None,
            end=self.end.isoformat() if self.end else None,
        )
