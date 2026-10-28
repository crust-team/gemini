# In-memory data

`gm.Dataset` owns one pandas-backed, sorted, unique, timezone-aware UTC table. Core data code
contains no file readers, database clients, network calls, or source handles. The user or
backend reads files/services and passes the resulting in-memory values to one of:

- `Dataset.from_frame(df, time_column=None, units=None, tz="UTC")`
- `Dataset.from_dict(data, time, units=None, tz="UTC")`
- `Dataset.from_records(rows, time_column, units=None, tz="UTC")`
- `Dataset.from_numpy(time, values, columns, units=None, tz="UTC")`
- `Dataset.from_profiles(profiles)`

`read(start, end)` and `window(start, end)` use inclusive bounds; `after(t)` is strict.
`native_step` is the median spacing. `fingerprint()` hashes timestamps, values, dtypes, and unit
metadata. Text flags are retained. When a constructor has no units, the engine uses the plant's
binding units. Missing bound columns are reported together before a run begins.

`Loader` is the internal sampler. It accepts any finite tick iterable and never imports engine
code. Exact and previous alignment use array search; mean alignment aggregates numeric values
over `[tick, next_tick)` and keeps the final text flag. A hold older than `max_gap` (by default
twice the native cadence) is a gap. Normal users do not construct loaders.

`Profile.constant(value, unit=..., clock=...)` and `Profile.from_series(series, unit=...)`
convert in-memory raw values to SI. Profiles combined into a dataset must share a clock.
