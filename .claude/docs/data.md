# In-memory data

`gm.Dataset` owns one pandas-backed, sorted, unique, timezone-aware UTC table of raw values; units
are metadata. The data package contains no file readers, database clients, network calls, or
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
values with offsets keep their own offsets, which may change at DST switches. The index may have
any resolution (s, ms, us or ns; pandas 3 parses text as microseconds); spacing, gaps and sampling
are computed in nanoseconds. `units` maps column names to a unit string or a
`{"unit": ..., "quantity": ...}` mapping. `from_profiles` takes a mapping of column names to
profiles that share one index and records their SI units. Invalid input (no time column, repeated
or missing timestamps, repeated or empty column names, unit metadata for unknown columns, a wrong
array shape) raises `gm.errors.RunError`.

`read(start, end, columns=None)` and `window(start, end)` use inclusive bounds; `after(t)` is
strict. `names` lists the columns, `start`/`end` the first and last timestamps, and
`native_step` is the median spacing (`None` for fewer than two rows). `unit(column, default)`
returns the unit recorded for a column, or `default` without metadata: during a run a column's
recorded unit replaces the unit in the plant binding, and the binding unit applies otherwise.
`fingerprint()` hashes timestamps, values, dtypes and unit metadata; checkpoints store it for
information only and nothing compares it on resume. Text flags are retained. Missing bound
columns are reported together, as one `ValidationError` (code `missing_column`), before a run begins.

**Run input.** `simulate`, `replay` and `live` take one format: a `Dataset`, or a pandas DataFrame
with a timezone-aware `DatetimeIndex` and columns named by the binding `column`, in the units of
the bindings (a unit recorded in the `Dataset` metadata replaces the binding's, as above).
`gemini.utils.data.dataset.as_dataset(data)` is the one wrapper: a `Dataset` passes through, a
DataFrame becomes a `Dataset` (any zone is converted to UTC), and a naive index, a non-time index
or another type raises `RunError`, because a local time without a zone is ambiguous. Rows with
NaN in a bound column are skipped for the twin that needs them and reported as `missing_value`
rows by `Results.errors()`; the run continues ([engine.md](engine.md#run-input)).

`Loader(dataset, ticks, columns=None, align="previous", max_gap=None, chunk=7 days,
durations=None)` is the internal sampler. It accepts any finite tick iterable and never imports
engine code. It yields `Sample(t, dt, row)`: the tick, the seconds to the next tick and a dict of
raw column values. `durations` gives those seconds per tick; by default they are the tick spacing
followed by the native cadence. `previous` alignment holds the latest row at or before the tick,
`exact` requires a row at the tick and `mean` averages numeric values over `[tick, next_tick)` and
keeps the final text flag. A hold older than `max_gap` (by default twice the native cadence, or
twice `DEFAULT_STEP` for fewer than two rows) and an empty mean bin give a row of NaN, which the
engine reports as missing measurements. The dataset is read one `chunk` of ticks at a time.
`Loader.arrays()` is the one alignment: `Aligned(times, durations, columns)` with one array per
column, for every `align` (gaps are NaN; a column is `float64`, or `object` when the dataset holds
text). Iterating yields the `Sample` of each tick built from those arrays, one chunk at a time.
`Aligned.numbers(column)` converts a column to floats (what `float()` refuses is NaN) and
`Aligned.present(column)` is the "missing" rule: a row holds a value when it is a finite number.
Tests assert that iteration equals the arrays, gaps, `max_gap` and chunk borders included.
Normal users do not construct loaders.

A frame may state units in `attrs["units"]`, as a `gm.schedule` plan does; they are the metadata of
its `Dataset`, so they replace a binding's unit, and a unit of a column the frame no longer has is
dropped.

`Profile.constant(value, unit=..., clock=...)` and `Profile.from_series(series, unit=...)`
convert in-memory raw values to SI. Profiles combined into a dataset must share a clock.

## Demand profiles

`gm.profiles` holds the two demand profiles of the challenge. `names()` lists them
(`heating_demand`, `cooling_demand`). `demand()` both in one frame, `get(name)` returns a DataFrame in the run-input format: 365
UTC days of 2027, a `DatetimeIndex` called `time`, one column named after the profile in W, and
`frame.attrs` with `units`, `quantities`, `description` and `source`, which names the organiser
file. The two files in `inputs/hackathon/` are the organisers' CSV files, unchanged; their
name, unit and description live in Python in `PROFILES` of `profiles/library.py`, and `get` raises
`inputs_missing` outside a source checkout. `profile_schema()`
is the JSON Schema of the same frame as a document: `name`, `description`, `source`, `columns` (unit
and quantity), `time` and `values`. A profile column becomes a run input when a plant binding names
it as its `column`.

The committed CSVs under `inputs/doublet_heat/` are immutable source data. Two
of their naming choices predate the naming rule and stay: columns named `*.m_dot` hold volumetric
flow in m3/s (their bindings declare `"unit": "m3/s"`), and the unbound status columns
(`esp_status`, `hex_status`, `filterA_status`, `filterB_status`) and
`production_wellhead_pressure` keep their old names.

## Where data lives

There is one data folder, and no data file inside `gemini/`: a plant is a class.

`inputs/` is at the repository root, next to `gemini/`, and is not installed. It holds everything
that code reads: `hackathon/` (the organisers' files, with a README), `plants/` (example values: a
`size`, `params`, `fluids`, `boundary`, `bindings`, `param_history` and `inputs`, those of the five
template plants the challenge's, with sizes the example assumes),
`doublet_heat/` (measured data) and `legacy_project/`. A function that needs it raises `RunError`
with code `inputs_missing` when it is absent, as in an installed wheel, and the message names the
file. Nothing fails at import time, and `gm.plants.get` works without it.

`docs/schemas/` is generated documentation, not data. `tests/fixtures/` holds goldens and
`tests/e2e/expected/` example outputs. `gemini/utils/paths.py` is the one place that knows where the
folder is, and `tests/unit/test_code_quality.py` checks the layout.
