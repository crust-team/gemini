"""Per-module series, energy integration and lossless result persistence."""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from gemini.core.types.flows import FuelFlow, HeatFlow, PowerFlow, Stream


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

    def __str__(self):
        """Use the same concise view for print and interactive display."""
        return self.__repr__()


class ModuleSeries:
    """Attribute access to a module's output series."""

    def __init__(self, frame):
        """Retain the module's field-indexed frame."""
        self._frame = frame

    def __getattr__(self, field):
        """Return one pandas Series or an informative unknown-field error."""
        if field not in self._frame:
            raise AttributeError(f"Unknown result field {field!r}; available: {list(self._frame)}")
        return self._frame[field]


class Results:
    """Collect finite timestep outputs, energy ports, health, errors and explicit skips."""

    def __init__(self):
        """Start an independent result table."""
        self._rows, self._times, self._dt = [], [], []
        self.skip_counts, self.errors = {}, []
        self._energy = set()
        self._skips = []
        self._frame = None

    def append(self, at, results, dt=0, skips=None, errors=None):
        """Append one completed step; count leaf energy ports once."""
        row = {}
        for path, (result, health) in results.items():
            row.update({(path, key): value for key, value in result.outputs.model_dump().items()})
            streams = [
                flow
                for flow in (result.inlets | result.streams).values()
                if isinstance(flow, Stream)
            ]
            row[path, "operating"] = any(flow.m_dot != 0 for flow in streams) if streams else True
            for port, flow in result.streams.items():
                if isinstance(flow, (PowerFlow, FuelFlow, HeatFlow)):
                    key = (path, "energy_port_" + port)
                    row[key] = flow.Q if isinstance(flow, HeatFlow) else flow.P
                    self._energy.add(key)
            if health is not None:
                values = health.model_dump()
                metrics = values.pop("metrics")
                row.update({(path, "health_" + key): value for key, value in values.items()})
                row.update(
                    {(path, "health_metric_" + key): value for key, value in metrics.items()}
                )
        self._times.append(at)
        self._dt.append(dt)
        self._rows.append(row)
        self._skips.append(skips or {})
        for path, reasons in (skips or {}).items():
            target = self.skip_counts.setdefault(path, {})
            for reason, count in reasons.items():
                target[reason] = target.get(reason, 0) + count
        self.errors.extend(dict(error, timestamp=at.isoformat()) for error in (errors or []))
        self._frame = None

    def __len__(self):
        """Count completed ticks, including skipped or failed rows."""
        return len(self._times)

    def __getitem__(self, path):
        """Expose module outputs as pandas Series through attributes."""
        return ModuleSeries(self.to_frame()[path])

    def to_frame(self):
        """Return a copy with (module_path, field) MultiIndex columns."""
        if self._frame is None:
            self._frame = pd.DataFrame(
                self._rows, index=pd.DatetimeIndex(self._times, name="timestamp")
            )
            self._frame.columns = pd.MultiIndex.from_tuples(
                self._frame.columns, names=["module_path", "field"]
            )
        return self._frame.copy()

    def summary(self):
        """Report energy per port (J/MWh), peaks, evaluated hours, alarms and skip reasons."""
        frame = self.to_frame()
        rows = []
        paths = sorted(
            set(frame.columns.get_level_values(0))
            | self.skip_counts.keys()
            | {error["module"] for error in self.errors}
        )
        dt = pd.Series(self._dt, index=frame.index, dtype=float)
        for path in paths:
            fields = (
                frame[path]
                if path in frame.columns.get_level_values(0)
                else pd.DataFrame(index=frame.index)
            )
            active = fields.notna().any(axis=1)
            alarms = fields.get("health_alarm", pd.Series(False, index=frame.index)).eq(True)
            info = dict(
                module=path,
                hours=float(dt[active].sum() / 3600),
                operating_hours=float(dt[fields.get("operating", active).eq(True)].sum() / 3600),
                errors=sum(error["module"] == path for error in self.errors),
                peaks={
                    field: float(fields[field].max())
                    for field in fields
                    if not field.startswith(("health_", "energy_port_"))
                    and field != "operating"
                    and pd.api.types.is_numeric_dtype(fields[field])
                },
                alarms=int(alarms.sum()),
                alarm_rate=float(alarms[active].mean()) if active.any() else 0,
                skipped=sum(self.skip_counts.get(path, {}).values()),
                reasons=dict(self.skip_counts.get(path, {})),
            )
            ports = sorted(key for key in self._energy if key[0] == path)
            for _, field in ports:
                power = fields[field]
                energy = float((power * dt).sum())
                rows.append(
                    info
                    | dict(
                        port=field.removeprefix("energy_port_"),
                        energy_J=energy,
                        energy_MWh=energy / 3.6e9,
                        peak_W=float(power.max()),
                    )
                )
            if not ports:
                power_fields = [
                    name for name in ("duty", "power", "thermal_power") if name in fields
                ]
                peak = float(fields[power_fields].max().max()) if power_fields else np.nan
                rows.append(info | dict(port="", energy_J=0.0, energy_MWh=0.0, peak_W=peak))
        return Summary(pd.DataFrame(rows).set_index(["module", "port"])) if rows else Summary()

    def __repr__(self):
        """Print a compact human-readable summary."""
        return str(self.summary())

    def save_csv(self, path):
        """Export a conventional analysis CSV with two header rows."""
        self.to_frame().to_csv(path)

    def save_parquet(self, path):
        """Export a conventional analysis Parquet file."""
        self.to_frame().to_parquet(path)

    def save(self, path):
        """Save exact cell values plus metadata; use Parquet when installed, otherwise CSV.

        Cells are JSON-encoded to retain lists, flags, full float precision and missing values.
        Returns the actual data filename; load accepts that filename or the original basename.
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
        encoded = frame.map(lambda v: json.dumps(v, allow_nan=True))
        encoded.columns = [str(i) for i in range(len(frame.columns))]
        encoded.index = [t.isoformat() for t in frame.index]
        if path.suffix == ".parquet":
            encoded.to_parquet(path)
        else:
            encoded.to_csv(path)
        metadata = dict(
            columns=list(frame.columns),
            dt=self._dt,
            skip_counts=self.skip_counts,
            errors=self.errors,
            skips=self._skips,
            energy=sorted(self._energy),
        )
        Path(str(path) + ".json").write_text(json.dumps(metadata, indent=2))
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
        metadata = json.loads(Path(str(path) + ".json").read_text())
        frame = (
            pd.read_parquet(path)
            if path.suffix == ".parquet"
            else pd.read_csv(path, index_col=0, dtype=str, keep_default_na=False)
        )
        frame = frame.map(json.loads)
        frame.columns = pd.MultiIndex.from_tuples(
            metadata["columns"], names=["module_path", "field"]
        )
        result = cls()
        result._times = pd.to_datetime(frame.index, utc=True).to_pydatetime().tolist()
        result._rows = frame.to_dict("records")
        result._dt, result.skip_counts = metadata["dt"], metadata["skip_counts"]
        result.errors = metadata["errors"]
        result._skips = metadata["skips"]
        result._energy = {tuple(key) for key in metadata["energy"]}
        return result

    def slice(self, start):
        """Return the new rows of a live call, with matching durations and diagnostics."""
        result = Results()
        result._times, result._rows, result._dt = (
            self._times[start:],
            self._rows[start:],
            self._dt[start:],
        )
        result._energy = self._energy.copy()
        result._skips = self._skips[start:]
        for skipped in result._skips:
            for path, reasons in skipped.items():
                target = result.skip_counts.setdefault(path, {})
                for reason, count in reasons.items():
                    target[reason] = target.get(reason, 0) + count
        times = {t.isoformat() for t in result._times}
        result.errors = [error for error in self.errors if error["timestamp"] in times]
        return result
