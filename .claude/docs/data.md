# In-memory data

`gm.Dataset` owns one pandas-backed, sorted, unique, timezone-aware UTC table of raw values; units
are metadata. Core data code contains no file readers, database clients, network calls, or
source handles. The user or backend reads files/services and passes the resulting in-memory
values to one of:

- `Dataset.from_frame(df, time_column=None, units=None, tz="UTC")`
- `Dataset.from_dict(data, time, units=None, tz="UTC")`
- `Dataset.from_records(rows, time_column, units=None, tz="UTC")`
- `Dataset.from_numpy(time, values, columns, units=None, tz="UTC")`
- `Dataset.from_profiles(profiles)`
- `Dataset(frame, units=None)` for a frame that already has a time index

The time axis may be any timestamp sequence: datetimes, ISO text or values with UTC offsets.
Naive timestamps are local times in `tz` and fail when ambiguous or nonexistent at a DST switch;
values with offsets keep their own offsets, which may change at DST switches. `units` maps column
names to a unit string or a `{"unit": ..., "quantity": ...}` mapping. `from_profiles` takes a
mapping of column names to profiles that share one index and records their SI units. Invalid
input (no time column, repeated or missing timestamps, repeated or empty column names, unit
metadata for unknown columns, a wrong array shape) raises `gm.errors.DatasetError`.

`read(start, end, columns=None)` and `window(start, end)` use inclusive bounds; `after(t)` is
strict. `names` lists the columns, `start`/`end` the first and last timestamps, and
`native_step` is the median spacing (`None` for fewer than two rows). `unit(column, default)`
returns the unit recorded for a column, or `default` without metadata: during a run a column's
recorded unit replaces the unit in the plant binding, and the binding unit applies otherwise.
`fingerprint()` hashes timestamps, values, dtypes and unit metadata; checkpoints store it for
information only and nothing compares it on resume. Text flags are retained. Missing bound
columns are reported together, as one `BindingError`, before a run begins.

`Loader(dataset, ticks, columns=None, align="previous", max_gap=None, chunk=7 days,
durations=None)` is the internal sampler. It accepts any finite tick iterable and never imports
engine code. It yields `Sample(t, dt, row)`: the tick, the seconds to the next tick and a dict of
raw column values. `durations` gives those seconds per tick; by default they are the tick spacing
followed by the native cadence. `previous` alignment holds the latest row at or before the tick,
`exact` requires a row at the tick and `mean` averages numeric values over `[tick, next_tick)` and
keeps the final text flag. A hold older than `max_gap` (by default twice the native cadence, or
twice `DEFAULT_STEP` for fewer than two rows) and an empty mean bin give a row of NaN, which the
engine reports as missing measurements. The dataset is read one `chunk` of ticks at a time.
Normal users do not construct loaders.

`Profile.constant(value, unit=..., clock=...)` and `Profile.from_series(series, unit=...)`
convert in-memory raw values to SI. Profiles combined into a dataset must share a clock.

The committed example CSVs under `examples/shared/doublet_heat/` are immutable source data. Two
of their naming choices predate the naming rule and stay: columns named `*.m_dot` hold volumetric
flow in m3/s (their bindings declare `"unit": "m3/s"`), and the unbound status columns
(`esp_status`, `hex_status`, `filterA_status`, `filterB_status`) and
`production_wellhead_pressure` keep their old names.
