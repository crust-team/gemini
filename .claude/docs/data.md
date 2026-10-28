# Datasets and sampling

Every engine input is a `gm.Dataset`. Reads use inclusive bounds and UTC indexes; naive times
are UTC unless `from_csv(..., tz=...)` explicitly supplies a timezone. Duplicate timestamps
are rejected. Text columns such as Normal/status flags are retained. The source cadence is
median timestamp spacing; the supplied 17,280-row CSV has a 15-minute native step.

- `Dataset.from_csv(path, time_column="Timestamp", sep=None, tz="UTC", units=None)` detects
  comma/semicolon delimiters and retains raw values.
- `Dataset.from_frame(df, units=None)` copies and sorts a time-indexed frame.
- `Dataset.from_profiles(profiles)` requires matching profile indexes. Profiles store SI
  values and units, so the engine does not convert them twice.
- `Dataset.from_csv_driver(project_folder)` wraps the existing connector. It refreshes when
  the CSV modification time or size changes, making repeated live calls inexpensive.
- `Dataset.from_influx(url, token, org, bucket, tags)` uses `token` as an environment-variable
  name, for example `INFLUXDB_TOKEN`. Tags explicitly select `plant_name` and `asset_name`.
  The existing connector discovers fields and bounds; irregular timestamps are retained.
- `Dataset.from_aveva(parameters, streams, start, end, step="15min",
  secret_env="AVEVA_CLIENT_SECRET")` wraps existing paginated interpolation. `streams` maps
  column names to AVEVA stream IDs; parameters contain service settings, never credentials.

Remote unit tests use injected transports. AVEVA's real integration test requires configured
credentials; no external service is needed for normal package tests or examples.

`dataset.window(start, end)` creates an inclusive bounded view. `describe()` retains source
paths/options and units. In-memory frames/profiles embed samples at full float precision;
file and remote sources retain reopening handles rather than copying their contents. Resuming
therefore assumes those referenced sources have not changed. Descriptions contain environment
names, never token/client-secret values. Empty datasets have no start/end and produce empty runs.

Units are metadata (`ColumnInfo`). Plant bindings supply raw units unless the dataset explicitly
provides them. Bound volume rates become mass rates only after the appropriate fluid density
is known. Replay validates all selected bound columns at once; missing values within an existing
column skip only the owning measured twin. Simulation uses root bindings and saved root defaults.
The default secondary boundary is an explicit assumption, not an inferred measurement.

`Loader` is an internal sampler in `core.data`; it accepts any finite iterable of ticks and
imports no engine code. The default read chunk is seven days. It uses arrays and search indexes,
not pandas row access. Previous sampling holds the latest observation only within `max_gap`
(default twice native cadence; one hour is the fallback cadence when unknown). Exact sampling
requires identical timestamps. Mean sampling averages numeric values in `[tick, next_tick)`
and uses the final text flag in each bin. Overlapping reads retain preceding values at chunk
boundaries without duplicate output samples. Every `Sample` includes timestamp, dt in seconds,
raw row, missing names and a gap flag. A missing mean bin remains missing.

`Profile.constant(value, unit=..., clock=...)` converts the raw constant to SI; the existing
explicit named SI constructor is also supported. `Profile.from_csv(path, column, unit)` reads
and converts one column. Profiles must be explicitly resampled before combining unequal grids.
