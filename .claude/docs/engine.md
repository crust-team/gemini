# Engine

`Engine(callbacks=None, on_error="record")` runs a plant on a finite clock.
`simulate(plant, dataset, clock)` evaluates handwritten plant wiring from root-bound assumptions.
`replay(plant, dataset, clock=None, start=None, end=None, only=None)` evaluates equipment twins on
measured boundaries. `live(plant, dataset, checkpoint, step=None, now=None, sink=None)` evaluates
only newly supplied timestamps. All calls are finite; scheduling, sleeping, and fetching new data
belong to the caller.

The pieces fit together as follows: the plant `Module` owns its design and bindings, the
in-memory `Dataset` holds raw observations, the internal `Loader` aligns rows to the engine
`Clock`, one private `Engine._run` loop evaluates every tick and calls the callbacks,
`save_checkpoint`/`load_checkpoint`/`resume` persist and continue a run, and `optim.calibrate`
fits parameters by calling `Engine.replay`.

## Clocks

`Clock(ticks, step=None)` holds strictly increasing UTC ticks; invalid ticks raise `ClockError`.
`Clock.days(year, month, day, days=1, step="1h", tz="UTC")` and `Clock.year(year, step="1h",
tz="UTC")` cover local calendar days, so a daily step follows local midnight and DST days have 23
or 25 hourly ticks. `Clock.range(start, end, step)` is an inclusive fixed grid, and
`Clock.from_data(dataset, step=None)` uses the observation times or a regular grid over the data.
Durations accept seconds (including NumPy integers), timedeltas and strings such as `15min`.
`dt(t)` returns seconds to the next tick, `durations` all of them; the final interval is `step`,
else the median spacing, else `DEFAULT_STEP` (one hour). `after(t)` and `window(start, end)`
select ticks and keep the final step.

## Runs

One binding plan is compiled per run, and binding errors raise `BindingError` before the first
step: missing bound columns, `only` paths without measured bindings, and volumetric flow columns
bound to a kg/s input that cannot be converted (a control or boundary on a module without
`pressure` and `temperature` parameters, or an inlet without `p` and `T`). A column's unit in the
dataset metadata replaces the binding's unit.

Simulation binds every leaf control and boundary to its binding's column, or else to a column
named after its dotted path; an input with neither needs a default or a persisted value. Each
step applies the values with `plant.set_inputs`, then calls the plant with the root inlets, built
from root bindings over `plant.boundary["root_inputs"]`. A missing value skips the whole step,
counted under the root path `""`. Replay applies each bound twin's controls and boundaries with
`module.set_inputs` before calling it with only its measured inlets, and skips only the twin
missing a required observation. Both therefore leave the last tick's inputs persisted on the
supplied plant. Replay and simulation apply dated parameters at each transition and convert raw
units at the boundary: volumetric flows become mass flows with the fluid density, and difference
quantities convert by scale only.

State bound to a sensor is authoritative for that tick; otherwise `module.step` integrates the
previous state. A twin skipped for missing data keeps its previous state, and the skipped tick's
`dt` is not integrated. After each replayed twin the engine calls `module.health(result,
measured)`; a module without a diagnostic is recorded as `assessed=False`.

Under `on_error="record"` an ordinary exception becomes a recorded error: per twin when a replayed
twin fails, otherwise (always in simulation) for the whole step with module path `""`, in which
case the module states are also restored to their value before the step. Under
`on_error="raise"` a failing replay twin raises `StepError` with the cause chained, and a failing
simulation step raises its exception.

## Replay through the graph

A replay is two phases (`gemini/core/engine/batch.py`). After `on_run_start` (so `EventLog` has
attached its hooks) the **batch phase** evaluates each twin once on arrays: for every stretch of
ticks that share one dated parameter snapshot it converts the bound columns to SI with the same
scale and offset as `units.to_si` (`units.si_conversion`), builds one stream of arrays per inlet,
and runs the cached graph (`gemini.graph`) over the rows that can be evaluated. A row is
**claimed** when every observation is present and finite, the inlet stream is valid, no check or
break node reaches an output, and every output and outlet value is finite (NaN only for a
declared `X | None` output, read back as `None`). The **commit phase** is the unchanged tick loop:
a twin takes a claimed row from the batch (a `ModuleResult` of plain Python floats, bools and
`None`, without `children` or `call_records`, built from per-row tuples prepared once and
unchecked `Ports` and `Values`) and runs `health` on it; every other row, of every
twin, is evaluated at its own tick on the plain path, which raises the exact error, `StepError`
chain, skip or result an untraced replay gives. Results, skips, errors, callbacks and checkpoints
therefore come from one code path.

Twins the graph cannot carry run entirely on the plain path: stateful twins (they need
`scan`), float32 runs, an untraceable twin, and every twin when one twin is a composite with
another twin below it. `engine.batch.reasons` gives the reason by twin path, `engine.batch.claims`
the claimed rows, and `claims[path].graph.breaks` the leaf children of a composite twin that run
untraced inside its graph. The batch is built only for `replay` (including `resume` of one), not
for `simulate` or `live`, and `gemini.graph.settings(traced=False)` turns it off.

The inputs a claimed row applies to its twin (`module.set_inputs`) are applied at once when the
engine has callbacks, else once at the end of the run (also on failure) for the last tick whose
inputs were not replaced by a plain-path tick, so the plant keeps the last tick's inputs. The
marked observer hooks of a twin (`EventLog`) are replayed for each claimed row, pre-hooks then
forward hooks, with that row's inlets, outlets, inputs and outputs. Dated parameters apply per
stretch in the batch phase and are restored afterwards; the commit loop applies them again. One
`GraphCache` lives on the `Engine`, so repeated replays (calibration) reuse graphs.

## Callbacks

Callbacks derive from `gemini.core.engine.callbacks.Callback` and run in registration order with
the engine as first argument: `on_run_start(engine)`, `on_step_start(engine, sample)`,
`on_step_end(engine, sample)` after results and position have committed, and
`on_run_end(engine)`. `on_error(engine, error)` observes only a failure that ends the run (an
exception in a step under `on_error="raise"`, in a callback or an interrupt), with
checkpoint-consistent state, before it propagates. Errors recorded under `on_error="record"` are
results: they are in `engine.results.errors` when `on_step_end` runs. `EventLog(path=None)`
writes JSON-lines events (in memory without a path), observes every module call through hooks that
it always removes at run end or failure, and records non-finite floats as `NaN`/`Infinity`.
`AutoCheckpoint(path, every=100)` saves every N steps or every elapsed duration such as `"1h"`.

## Results

`Results` is columnar. `Results.commit(chunk)` is the one way in: a `ResultChunk`
(`gemini/core/engine/chunks.py`) holds the ticks of one evaluation, whatever their number, one
included: `times`, `durations`, a `PathColumns` per module path and the per-tick `skips` and
`errors`. `PathColumns(present, columns)` has a boolean mask of the ticks the path was evaluated
for and one column per field, every column with one entry per tick (entries of absent ticks are
ignored). A column is a NumPy array or, for objects such as list outputs and message strings, a
Python list; `PathColumns.of(result, health, present)` takes them from a leaf `ModuleResult` and
a `Health` of arrays or scalars (scalars broadcast) and computes `operating` from the flows.
Columns are kept by reference. `Results.append(at, outputs, dt, skips, errors)` stays as the
one-tick form for plain results: the row waits as cells and joins the columns as one chunk when a
table, file or slice is wanted. Chunks are concatenated lazily in `to_frame`, which gives the
columns and dtypes a table built row by row would have: columns in the order of first appearance
(paths by the first tick they are present, then as given), a typed array that is present
everywhere keeps its dtype, floats with an absent tick are `float64` with NaN, and every other
column (booleans or integers with an absent tick, lists, strings, `None`) is read as pandas reads
a column of row values with NaN for absent ones. Energy fields and `operating` are computed from
the columns.

`Results[path]` returns the series of one module path; `Results[path].field` is a pandas Series
and an unknown path or field raises `UnknownResultError`. Only leaf results are stored: twins in
replay and the leaves of the plant call in simulation, not root or composite formula outputs.
`Results[path].get(field, unit=...)` converts only the six fields of `SERIES_UNITS` (`head`,
`pressure_drop`, `discharge_pressure`, `power`, `duty`, `thermal_power`), because results store no
per-field units; other fields raise `ValueError`. `to_frame()` returns a copy with
`(module_path, field)` MultiIndex columns, `summary()` reports energy per output, peaks, operating
hours, alarms, skips and errors, `skip_counts` and `errors` hold the diagnostics, and
`save(path)`/`Results.load(path)` keep every cell exactly: as Parquet when `pyarrow` is installed,
otherwise as CSV, each with a JSON metadata sidecar.

## Checkpoints

The version-1 JSON manifest stores the run kind, the importable plant class, `plant.to_dict()`,
module states, the finite clock, the completed position, the original dataset fingerprint
(informational only), selected `only` paths, the error policy, the runtime settings captured at
run start, the creation time and sibling filenames. Results and unfinished replay/simulation rows
are written first, then the manifest is atomically replaced. The stored rows start `max_gap`
before the position, because a held previous row may still supply the next ticks; they use
JSON-encoded CSV cells to preserve exact float bits, and their JSON sidecar records the column
units and the run's `max_gap`, which a resumed run reuses. A checkpoint never depends on the file
or service that originally supplied data.

`Engine.load_checkpoint(path, callbacks=None)` rebuilds the plant from the manifest and restores
the run state with the saved error policy. `resume()` continues strictly after the saved
position, or returns the stored results when the clock is finished; a resumed run gives the same
results as an uninterrupted one. Resume and live calls re-apply the saved precision and display
units, but not the default fluid, which only seeds newly built modules and streams.

## Live runs

`live` evaluates the supplied plant. An existing live checkpoint must have been saved for a plant
of the same class; it contributes the committed position, results, module states, clock step and
runtime settings, while the engine's callbacks and error policy stay the caller's. Ticks run up
to `min(now, newest row)`, with `now` defaulting to the current UTC time. Without `step` the
ticks are the new rows, and a call with fewer than two rows reuses the checkpointed step for its
final interval. With `step` the ticks are a fixed grid anchored at the committed position (the
first call anchors it at the first supplied row), so the grid stays the same across calls.

Live checkpoints intentionally store no input rows: each external call supplies its new data.
Rows at or before the committed watermark are ignored; repeated/overlapping calls therefore
process each tick once. The call returns only its new rows, while the engine and checkpoint keep
the cumulative results. The checkpoint commits before an optional `sink(new_results)`, so sinks
should upsert by timestamp. There is no distributed transaction with an external sink.
