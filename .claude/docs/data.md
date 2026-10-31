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

`gm.profiles` ships no profile: a demand is the caller's. `from_csv(path, columns, unit,
time_column=None)` reads a file, and `columns` maps its columns to the quantities of gemini, so a
file adapts to gemini and gemini takes no name or unit from it. `from_values(values, unit, start,
step, quantity)` takes numbers. A quantity is `heating_demand` or `cooling_demand`. Both return a
DataFrame in the run-input format, the `demand` of `gm.schedule`: a UTC `DatetimeIndex` called `time`
at any constant step and of any length, one column per quantity in W, and `frame.attrs` with `units`
and `quantities`. Both validate through one check: a monotonic index with no gaps or repeats, a
constant step, no negative or missing value, a known quantity. `profile_schema()` is the JSON Schema
of the same frame as a document: `columns` (unit and quantity), `time` and `values`. A profile column
becomes a run input when a plant binding names it as its `column`.

The committed CSVs under `inputs/doublet_heat/` are immutable source data. Two
of their naming choices predate the naming rule and stay: columns named `*.m_dot` hold volumetric
flow in m3/s (their bindings declare `"unit": "m3/s"`), and the unbound status columns
(`esp_status`, `hex_status`, `filterA_status`, `filterB_status`) and
`production_wellhead_pressure` keep their old names.

## Where data lives

There is one data folder, and no data file inside `gemini/`: a plant is a class.

`inputs/` is at the repository root, next to `gemini/`, and is not installed. It holds everything
that code reads: `examples/` (sample problems), `plants/` (example values: a `size`, `params`,
`fluids`, `boundary`, `bindings`, `param_history` and `inputs`; the template plants have none),
`doublet_heat/` (measured data) and `legacy_project/`. A function that needs it raises `RunError`
with code `inputs_missing` when it is absent, as in an installed wheel, and the message names the
file. Nothing fails at import time, and `gm.plants.get` works without it.

`inputs/examples/<problem>/` holds one folder per sample problem, a whole problem in the shapes of
gemini: its source files with a README, `plant.json` (a plant dict), `rules.json` (the rules of
`gm.schedule`), `limits.json` (a `gm.checks.Limits` dict) and `assumptions.json` when it uses prices.
`hackathon_2027/` and `shallow_district/` are the two today. **Only `examples/` and `tests/` read this
folder**: nothing under `gemini/` names it, or a problem, and `tests/unit/test_code_quality.py` checks
that. A problem is a test of the code, never the source of a default, a name or a structure.

`docs/schemas/` is generated documentation, not data. `tests/fixtures/` holds goldens and
`tests/e2e/expected/` example outputs. `gemini/utils/paths.py` is the one place that knows where the
folder is, and `tests/unit/test_code_quality.py` checks the layout.
