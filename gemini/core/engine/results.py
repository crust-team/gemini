"""Per-module series, energy integration and lossless result persistence."""

from pathlib import Path

import numpy as np
import pandas as pd

from gemini.core.engine.chunks import (
    PathColumns,
    ResultChunk,
    assemble,
    first_present,
    merge,
)
from gemini.core.physics import units
from gemini.errors import UnitError, UnknownResultError
from gemini.utils.files import read_cells, write_cells
from gemini.utils.strings import did_you_mean, join_names

ENERGY_FIELDS = ("electricity", "fuel", "heat_loss")
"""Leaf outputs integrated over time into energy totals."""

SERIES_UNITS = {
    "head": ("Pa", "pressure_difference"),
    "pressure_drop": ("Pa", "pressure_difference"),
    "discharge_pressure": ("Pa", "pressure"),
    "power": ("W", "power"),
    "duty": ("W", "power"),
    "thermal_power": ("W", "power"),
}
"""Stored SI unit and quantity of the result fields that ``ModuleSeries.get`` can convert."""


class Summary(pd.DataFrame):
    """Detailed summary table with a compact printed energy/alarm view."""

    def __repr__(self):
        """Display the principal metrics without pandas hiding energy or alarm columns."""
        if self.empty:
            return "No completed observations"
        columns = [
            "energy_J",
            "energy_MWh",
            "peak_W",
            "operating_hours",
            "alarms",
            "alarm_rate",
            "skipped",
            "errors",
        ]
        return self[columns].to_string(float_format=lambda value: f"{value:.6g}")

    __str__ = __repr__


class ModuleSeries:
    """Attribute access to a module's output series."""

    def __init__(self, frame, path=""):
        """Retain the module's field-indexed frame and its path for error messages."""
        self._frame = frame
        self._path = path

    def __getattr__(self, field):
        """Return one pandas Series or an informative unknown-field error."""
        if field not in self._frame:
            raise UnknownResultError(
                f"{self._path}: result field = {field!r}; expected one of "
                f"{join_names(self._frame)}{did_you_mean(field, self._frame)}"
            )
        return self._frame[field]

    def get(self, field, unit=None):
        """Return a series, optionally converted from its stored SI unit.

        Results store no per-field unit metadata, so conversion is limited to the fields in
        ``SERIES_UNITS`` (head, pressure drops, powers and duties); other fields raise.
        """
        series = getattr(self, field)
        if unit is None:
            return series
        if field not in SERIES_UNITS:
            raise UnitError(
                f"{self._path}: result field = {field!r}; expected one of "
                f"{join_names(SERIES_UNITS)} for unit conversion"
            )
        source, quantity = SERIES_UNITS[field]
        return series.map(lambda value: units.convert(value, source, unit, quantity))


def _add_skips(skip_counts, skips):
    """Add one step's ``{path: {reason: count}}`` skips into running totals."""
    for path, reasons in skips.items():
        target = skip_counts.setdefault(path, {})
        for reason, count in reasons.items():
            target[reason] = target.get(reason, 0) + count


class Results:
    """Collect finite timestep outputs, energy totals, health, errors and explicit skips.

    Results are columnar. ``commit(chunk)`` is the one way in: a ``ResultChunk`` of any length,
    one tick included. Chunks concatenate lazily in ``to_frame``.
    """

    def __init__(self):
        """Start an independent result table."""
        self._chunks, self._order = [], {}
        self._times, self._dt = [], []
        self.skip_counts, self.errors = {}, []
        self._energy = set()
        self._skips = []
        self._frame = None

    def commit(self, chunk):
        """Commit a chunk of ticks: its columns, durations, skips and errors."""
        self._register(chunk)
        self._record(chunk.times, chunk.durations, chunk.skips, chunk.errors)

    def _record(self, times, durations, skips, errors):
        """Keep the times, durations, skips and errors of committed ticks."""
        self._times.extend(times)
        self._dt.extend(durations)
        self._skips.extend(skips if skips is not None else [{}] * len(times))
        for skipped in skips or ():
            _add_skips(self.skip_counts, skipped)
        for row, error in errors:
            self.errors.append(dict(error, timestamp=times[row].isoformat()))
        self._frame = None

    def _register(self, chunk):
        """Store a chunk: its new columns, in the order a row-by-row build meets them."""
        for key in chunk.column_order():
            self._order.setdefault(key, None)
        for path, table in chunk.tables.items():
            if table.present.any():
                self._energy.update((path, name) for name in ENERGY_FIELDS if name in table.columns)
        self._chunks.append(chunk)

    def __len__(self):
        """Count completed ticks, including skipped or failed rows."""
        return len(self._times)

    def __getitem__(self, path):
        """Expose module outputs as pandas Series through attributes."""
        frame = self._cached_frame()
        paths = list(frame.columns.get_level_values(0).unique())
        if path not in paths:
            raise UnknownResultError(
                f"Results: module path = {path!r}; expected one of "
                f"{join_names(paths)}{did_you_mean(path, paths)}"
            )
        return ModuleSeries(frame[path].copy(), path)

    def _cached_frame(self):
        """Return the shared table, built once after each append; callers must not change it."""
        if self._frame is None:
            self._chunks = [merge(self._chunks)] if self._chunks else []
            chunk = self._chunks[0] if self._chunks else ResultChunk([], [], {})
            self._frame = assemble(chunk, list(self._order), self._times)
        return self._frame

    def to_frame(self):
        """Return a copy with (module_path, field) MultiIndex columns."""
        return self._cached_frame().copy()

    def summary(self):
        """Report energy per port (J/MWh), peaks, evaluated hours, alarms and skip reasons."""
        frame = self.to_frame()
        recorded = set(frame.columns.get_level_values(0))
        paths = sorted(
            recorded | self.skip_counts.keys() | {error["module"] for error in self.errors}
        )
        dt = pd.Series(self._dt, index=frame.index, dtype=float)
        rows = []
        for path in paths:
            fields = frame[path] if path in recorded else pd.DataFrame(index=frame.index)
            rows.extend(self._summary_rows(path, fields, dt))
        return Summary(pd.DataFrame(rows).set_index(["module", "port"])) if rows else Summary()

    def _module_info(self, path, fields, dt):
        """Return evaluated and operating hours, peaks, alarms, errors and skips of one path."""
        active = fields.notna().any(axis=1)
        alarms = fields.get("health_alarm", pd.Series(False, index=fields.index)).eq(True)
        return dict(
            module=path,
            hours=float(dt[active].sum() / 3600),
            operating_hours=float(dt[fields.get("operating", active).eq(True)].sum() / 3600),
            errors=sum(error["module"] == path for error in self.errors),
            peaks={
                field: float(fields[field].max())
                for field in fields
                if not field.startswith("health_")
                and (path, field) not in self._energy
                and field != "operating"
                and pd.api.types.is_numeric_dtype(fields[field])
            },
            alarms=int(alarms.sum()),
            alarm_rate=float(alarms[active].mean()) if active.any() else 0,
            skipped=sum(self.skip_counts.get(path, {}).values()),
            reasons=dict(self.skip_counts.get(path, {})),
        )

    def _summary_rows(self, path, fields, dt):
        """Return one row per energy output of a path, or one row with its peak power."""
        info = self._module_info(path, fields, dt)
        ports = sorted(field for owner, field in self._energy if owner == path)
        if not ports:
            power_fields = [name for name in ("duty", "power", "thermal_power") if name in fields]
            peak = float(fields[power_fields].max().max()) if power_fields else np.nan
            return [info | dict(port="", energy_J=0.0, energy_MWh=0.0, peak_W=peak)]
        rows = []
        for field in ports:
            power = fields[field]
            energy = float((power * dt).sum())
            rows.append(
                info
                | dict(
                    port=field,
                    energy_J=energy,
                    energy_MWh=energy / 3.6e9,
                    peak_W=float(power.max()),
                )
            )
        return rows

    def __repr__(self):
        """Print a compact human-readable summary."""
        return str(self.summary())

    def save(self, path):
        """Save exact cell values plus metadata; use Parquet when installed, otherwise CSV.

        Cells are JSON-encoded to retain lists, flags, full float precision and missing values.
        The format depends on whether ``pyarrow`` imports: a path without a ``.csv``/``.parquet``
        suffix gets the available one, and a ``.parquet`` path becomes ``.csv`` without it. A
        Parquet file, including one written for a checkpoint, therefore needs ``pyarrow`` to
        load. Returns the actual data filename; load accepts that filename or the original
        basename.
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            import pyarrow  # noqa: F401

            suffix = ".parquet"
        except ImportError:
            suffix = ".csv"
        if path.suffix not in {".parquet", ".csv"}:
            path = Path(str(path) + suffix)
        elif path.suffix == ".parquet" and suffix == ".csv":
            path = path.with_suffix(".csv")
        frame = self.to_frame()
        metadata = dict(
            columns=list(frame.columns),
            dt=self._dt,
            skip_counts=self.skip_counts,
            errors=self.errors,
            skips=self._skips,
            energy=sorted(self._energy),
        )
        write_cells(
            path, frame.set_axis([str(i) for i in range(len(frame.columns))], axis=1), metadata
        )
        return path

    @classmethod
    def load(cls, path):
        """Restore result cells and integration metadata without re-running equipment."""
        path = Path(path)
        if not path.exists():
            path = next(
                (
                    Path(str(path) + ext)
                    for ext in (".parquet", ".csv")
                    if Path(str(path) + ext).exists()
                ),
                path,
            )
        frame, metadata = read_cells(path)
        frame.columns = pd.MultiIndex.from_tuples(
            metadata["columns"], names=["module_path", "field"]
        )
        result = cls()
        times = pd.to_datetime(frame.index, utc=True).to_pydatetime().tolist()
        result._chunks = [_stored_chunk(frame, times, metadata)]
        result._order = dict.fromkeys(frame.columns)
        result._times = times
        result._dt, result.skip_counts = metadata["dt"], metadata["skip_counts"]
        result.errors = metadata["errors"]
        result._skips = metadata["skips"]
        result._energy = {tuple(key) for key in metadata["energy"]}
        return result

    def slice(self, start):
        """Return the new rows of a live call, with matching durations and diagnostics."""
        result = Results()
        if self._chunks:
            self._chunks = [merge(self._chunks)]
            chunk = self._chunks[0].sliced(start)
            result._chunks = [chunk]
            result._order = _sliced_order(self._order, chunk)
        result._times, result._dt = self._times[start:], self._dt[start:]
        result._energy = self._energy.copy()
        result._skips = self._skips[start:]
        for skipped in result._skips:
            _add_skips(result.skip_counts, skipped)
        times = {t.isoformat() for t in result._times}
        result.errors = [error for error in self.errors if error["timestamp"] in times]
        return result


def _sliced_order(order, chunk):
    """Return the columns of a slice: those of paths present in it, by first tick present."""
    first = {path: first_present(table) for path, table in chunk.tables.items()}
    kept = [key for key in order if first.get(key[0]) is not None]
    return dict.fromkeys(sorted(kept, key=lambda key: first[key[0]]))


def _stored_chunk(frame, times, metadata):
    """Return the whole loaded table as one chunk: every cell present, one list per column."""
    tables = {}
    for position, (path, name) in enumerate(frame.columns):
        table = tables.setdefault(path, PathColumns(np.ones(len(times), dtype=bool), {}))
        table.columns[name] = frame.iloc[:, position].tolist()
    return ResultChunk(list(times), list(metadata["dt"]), tables)
