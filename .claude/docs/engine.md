# Engine

## Functions or engine

A run has two levels and one implementation. `gm.simulate`, `gm.replay`, `gm.live` and `gm.resume`
(`gemini/engine/run.py`) are for everyday use: each builds an `Engine`, calls the matching method
and returns its `Results`, with no run logic of its own. `gm.Engine` stays public for complex
tasks: a stateful run over several calls, a callback that reads the engine, a live run held in
memory, a manual checkpoint.

```python
import gemini as gm

plant = gm.plants.example("DoubletHeatPlant")
results = gm.simulate(plant, profile)
print(results.summary(units={"power": "MW", "temperature": "degC"}))
```

No object is kept between calls of the functions, except the traced graphs, which the plant holds
(`gemini.graph.graph_cache`): calling a function hundreds of times on one plant traces it once,
and an `Engine` built on the plant shares the same graphs. The guards of
[`GraphCache`](native-engine.md) decide: a changed numeric parameter does not retrace, a changed
structure does. A copied or pickled plant starts with an empty cache.

The arguments are those of `Engine` and of the matching method, with `plant` first. On `simulate`
and `replay`, `checkpoint=path` writes a checkpoint at the end of the run, also one that stops
early (a `gm.errors.Cancelled` or a failure under `on_error="raise"`), replacing an existing file;
a run that never started (a binding error) writes nothing. `checkpoint_every` also writes it during
the run through `AutoCheckpoint` and needs `checkpoint`, or raises `ValidationError`.

The on_error default is `"raise"`, on the functions and on `gm.Engine`.

`gm.resume(checkpoint, callbacks=None)` is `Engine.load_checkpoint(path, callbacks).resume()`, and
it writes to the same file when the run ends or stops early. `checkpoint_every` is not stored in
the file: pass `callbacks=[AutoCheckpoint(path, every)]` for periodic saves on a resumed run. A live checkpoint raises `RunError` (code `checkpoint`) naming `gm.live`. The files are the ones `save_checkpoint`
writes, so either level resumes the other's.

`gm.live(plant, source, checkpoint, ...)` requires the path, which is all that carries a live run
between calls; `None` raises `ValidationError`. The first call with a path that does not exist yet
starts the run and writes it; every later call continues from it and updates it, as
`Engine.live(source, checkpoint)` does on a new engine ([Live runs](#live-runs)). The callbacks and
error policy of a call are the caller's, and a call that fails or is cancelled leaves the file as
it was, so its rows are processed again by the next call.

## Schedule

```python
plan = gm.schedule(plant, demand, rules={
    "order": ["geothermal", "heat_pump", "boiler"],
    "doublet_flow": {"min": "50 m3/h", "max": "300 m3/h"},
    "max_brine_cooling": "40 K",
    "operating_days": None})
results = gm.simulate(plant, plan)
```

`gm.schedule` (`gemini/analysis/schedule.py`, formulas in `physics/dispatch.py`) decides the controls
of each day of `demand` from a daily energy balance on the plant's design values, with no simulation
inside. It reads the `Doublet` children and at most one `HeatPump`, `Boiler`, `AbsorptionUnit`,
`HeatingGrid` and `CoolingGrid`. The chiller's heat is the cooling demand over its
`thermal_cop`. Sources follow `order`: each doublet, in plant order, runs at the flow that gives the
heat at `max_brine_cooling`, clipped to `doublet_flow`, below the minimum at the minimum with less
cooling. The heat pump and boiler take the `temperature_setpoint` set on them, the design's supply
temperatures, and cover what is left in the run. Unmet demand is no error: the run reports
`unmet_demand`.

The plan needs no bindings and changes nothing on the plant: **its columns are named after what they
drive**, so `gm.simulate(plant, plan)` binds them by the rule of a run, below. Leaf controls and
boundaries have a column named after their dotted path (`d0.reservoir.production_rate`,
`injection.split_fraction`), and a plant inlet field a column named `port.field`
(`heating_return.m_dot`); ports `heating_return` and `cooling_return` take their temperature from
`plant.boundary["root_inputs"]`. `boiler_duty`, `<doublet>.flow` and `<doublet>.is_running` are for
reading. `operating_days` is `None`, every doublet on every day; an integer or a list of outage dates
raises `NotImplementedYet` until the meaning of the organisers' "330 daily steps" is decided.

## The engine

`Engine(plant, backend="numpy", callbacks=None, on_error="raise")` runs one plant on a finite clock
and raises on a failure, unless `on_error="record"`.
`simulate(profile, clock=None)` evaluates the plant from root-bound assumptions.
`replay(data, start=None, end=None, state=None, clock=None, only=None)` evaluates equipment twins on
measured boundaries. `live(source, checkpoint=None, step=None, now=None, sink=None)` evaluates only
newly supplied timestamps. All calls are finite; scheduling, sleeping, and fetching new data
belong to the caller. Every call returns `Results`.

The pieces fit together as follows: the plant `Module` owns its design and bindings, the
in-memory `Dataset` holds raw observations, the internal `Loader` aligns rows to the engine
`Clock`, one private `Engine._run` hands the run to the `Runner`, which evaluates chunks of ticks and replays the callbacks,
`save_checkpoint`/`load_checkpoint`/`resume` persist and continue a run, and `optim.calibrate`
fits parameters by calling `Engine.replay` on a copy of the plant.

## Run input

One format serves `simulate`, `replay` and `live`: a `gm.Dataset`, or a pandas DataFrame with a
timezone-aware `DatetimeIndex` (any zone; the instants become UTC) and one column per binding
`column`. A DataFrame is wrapped by `gemini.utils.data.dataset.as_dataset`; a naive index, a
non-time index or any other object raises `RunError`. Values have the unit of the binding,
except that a unit recorded in `Dataset` metadata replaces it (the rule below stays). Without
`clock`, `simulate` and `replay` use the ticks of the input (`Clock.from_data`).

- **Missing columns.** Every bound column the input lacks is listed in one `ValidationError` (code
  `missing_column`, `suggestions` with the closest column), raised before
  the first step.
- **NaN rows.** A tick where a bound value is NaN, absent beyond `max_gap` or a text flag is not an
  error of the run: that twin is skipped at the tick, counted in `results.skip_counts`, listed in
  `results.errors()` with the code `missing_value`, and the run continues. A tick where a module
  raises is a row with the code of the failure (`invalid_inlet`, `out_of_bounds`, `out_of_range`,
  `no_convergence`, `module_error`; the table is `gm.errors.ROW_CODES`), under `on_error="record"`.

## Threads and backends

Plants and engines are not shared across threads. An engine keeps run state (results, position,
module states) and a plant keeps persisted inputs and traced graphs, so a worker loads its own plant
(`gm.plants.from_dict(...)`) and builds its own engine; settings from `gm.runtime` are
context-local and a new thread starts from the defaults.

`backend` is applied to every run of the engine with `gemini.backends.settings(backend=...)`:
`"numpy"` evaluates arrays, `"python"` evaluates row by row, and the numbers are the same (the
parity suite checks it). The backend is saved in checkpoints. An unknown name raises
`ValidationError` when the engine is built.

## Clocks

`Clock(ticks, step=None)` holds strictly increasing UTC ticks; invalid ticks raise `RunError`.
`Clock.days(year, month, day, days=1, step="1h", tz="UTC")` and `Clock.year(year, step="1h",
tz="UTC")` cover local calendar days, so a daily step follows local midnight and DST days have 23
or 25 hourly ticks. `Clock.range(start, end, step)` is an inclusive fixed grid, and
`Clock.from_data(dataset, step=None)` uses the observation times or a regular grid over the data.
Durations accept seconds (including NumPy integers), timedeltas and strings such as `15min`.
`dt(t)` returns seconds to the next tick, `durations` all of them; the final interval is `step`,
else the median spacing, else `DEFAULT_STEP` (one hour). `after(t)` and `window(start, end)`
select ticks and keep the final step.

## Runs

One binding plan is compiled per run, and binding errors raise `ValidationError` before the first
step: missing bound columns, `only` paths without measured bindings, and volumetric flow columns
bound to a kg/s input that cannot be converted (a control or boundary on a module without
`pressure` and `temperature` parameters, or an inlet without `p` and `T`). A column's unit in the
dataset metadata replaces the binding's unit.

Simulation binds every leaf control and boundary to its binding's column, or else to a column
named after its dotted path; an input with neither needs a default or a persisted value. A root
inlet field binds the same way, to its binding or to a column named `port.field`. Each
step applies the values to their modules, then calls the plant with the root inlets, built
from root bindings over `plant.boundary["root_inputs"]`. A missing value skips the whole step,
counted under the root path `""`. Replay applies each bound twin's controls and boundaries with
the module before calling it with only its measured inlets, and skips only the twin
missing a required observation. Both therefore leave the last tick's inputs persisted on the
supplied plant. Replay and simulation apply dated parameters at each transition and convert raw
units at the boundary: volumetric flows become mass flows with the fluid density, and difference
quantities convert by scale only.

State bound to a sensor is authoritative for that tick; otherwise `module.step` integrates the
previous state. A twin skipped for missing data keeps its previous state, and the skipped tick's
`dt` is not integrated. The engine assesses `module.health(result,
measured)` for each replayed twin (once on the arrays of a chunk); a module without a diagnostic
is recorded as `assessed=False`.

A run raises by default. Under `on_error="record"` an ordinary exception becomes a recorded error and the run continues: per twin when a replayed
twin fails, otherwise (always in simulation) for the whole step with module path `""`, in which
case the module states are also restored to their value before the step. Under
`on_error="raise"` a failing replay twin raises `RunError` with the cause chained, and a failing
simulation step raises its exception.

## The runner

`Engine.replay`, `live`, `simulate` and `resume` all reach `Engine._run`, which builds the
`BindingPlan` and the `Loader` arrays and hands them to `Runner` (`gemini/engine/runner.py`).
There is no tick loop and no second path for a failing row: a run is a list of **twins** (the
equipment twins of a replay; the plant in simulate) evaluated over **chunks** of ticks.

- **Chunks.** Ticks that share one dated parameter snapshot form a stretch (the snapshot is applied
  at its first tick). A chunk is the whole stretch, except that it is **one tick** when a stateful
  module is stepped (`Twin.stepped`), when a twin sits below another twin (its controls are read
  from what the other twin persisted this tick), or when a callback declares `changes_run = True`.
  `live` evaluates the ticks of one call as one chunk, like `replay`.
- **Per chunk and twin.** `columns.read` converts the bound columns to SI (`units.si_conversion`,
  volumetric flows with `flows.mass_flow`) and gives every tick a status in the order a plain call
  meets its problems: the first missing column (a skip counted by its name; the missing rule is
  `Aligned.present`), or an inlet stream the limits refuse (an error with the text of the real
  `Stream` constructor). `outcome.evaluate_twin` builds the inlet streams of the ticks that can be
  evaluated, takes the graph from the plant's `GraphCache` (`graph.breaks` per twin path are in
  `engine.graph_breaks`), feeds it with `graph_feeds` and calls `gemini.graph.evaluate`: the backend
  is the one of `gemini.backends.settings(backend=...)`, NumPy over arrays by default, Python row by
  row (`backend="python"` is how to debug) and the results are the same. A failing row gets the
  check's class and exact message from `Evaluation.error`; a bound violation on a declaration reads
  `declaration.validate`. Then `health.assess` runs `Module.health` once on the arrays (row by row on
  the Python backend, or when the call on arrays raises, which finds the rows whose health fails:
  they are errors), and the columns are spread over the chunk (`PathColumns.spread`).
- **Breaks.** A leaf that is stateful, pre-hooked, untraceable or has a hook that only reads is a
  break node. A root that cannot be traced as a whole (a plant with a loop or a constraint, float32
  precision, or a stateful module in a stepped run) is one **root break**: the real module, called
  row by row with its states, so its results are real `ModuleResult` trees (children and
  combinations exact). There is one implementation of a break, used by every mode.
- **Skips and errors.** A twin is skipped for the first missing column in this order: controls,
  boundaries, inlet fields (each inlet's stream is checked once its fields are read), observations,
  measured states. In simulate the plant is the one twin: root inlets, then the leaf inputs; a skip
  is counted under `""`. A failing row is recorded as the problem `path`, `code`, `message=str(error)`; in simulate, whatever fails is a whole-step error under `""` and the
  states stay as they were.
- **Inputs.** Each tick sets the module's controls and boundaries on its twin
  before the module is called, so a failing tick has persisted them; the runner sets them at the
  end of a chunk, for the last tick that applied them (one tick at a time when there are callbacks
  or one-tick chunks), so the plant keeps the last tick's inputs, as an interrupted run does.
- **States.** A stateful twin is a root break stepped once per tick with the run's state;
  `engine.module_states` is `{path: tree}` in replay and `{"": tree}` in simulate, as in a
  checkpoint. State bound to a sensor is passed as the start state and stays authoritative.
- **`on_error="raise"`.** The ticks before the first failing one are committed, their callbacks run,
  `on_step_start` of the failing tick is delivered and the error is raised: `RunError` chained to
  the cause in replay, the exception itself in simulate. A later twin of the failing tick is not
  evaluated when the chunk is one tick.

A direct call such as `esp(fluid_in=...)` stays eager: the same `forward` and ops.

## Callbacks

Callbacks derive from `gemini.engine.callbacks.Callback` and run in registration order with
the engine as first argument. They are **replayed from the results of a chunk**, tick by tick,
seeing the engine as a tick loop left it (results, position and states of that tick, the plant's
inputs); a callback that changes the run (the plant, its parameters or inputs, the dataset) sets
the class attribute `changes_run = True`, which makes the chunks one tick and calls
`on_step_start` before the tick is evaluated. Without callbacks a chunk is committed at once, with
callbacks one tick at a time: `on_run_start(engine)`, `on_step_start(engine, sample)`,
`on_step_end(engine, sample)` after results and position have committed, and
`on_run_end(engine)`. `on_error(engine, error)` observes only a failure that ends the run (an
exception in a step under `on_error="raise"`, in a callback or an interrupt), with
checkpoint-consistent state, before it propagates. Errors recorded under `on_error="record"` are
results: they are in `engine.results.errors()` when `on_step_end` runs. `EventLog(path=None)`
writes JSON-lines events (in memory without a path); after each tick it logs a `forward` event for
every module call of `engine.step_results` (the tick's `ModuleResult` tree by twin path, built
from the arrays when asked), children before the module that called them, with no hook on the
plant, and records non-finite floats as `NaN`/`Infinity`. A failing composite call logs no event
for the children that had completed.
`AutoCheckpoint(path, every=100)` saves every N steps or every elapsed duration such as `"1h"`.

**Progress and cancelling.** When callbacks are registered, `on_progress(engine, done, total)` runs
after `on_step_end` of every committed tick: `done` ticks of this run are committed out of
`total` (the ticks the call still has to evaluate). A callback stops a run cleanly by raising
`gm.errors.Cancelled` (code `cancelled`) from `on_step_end` or `on_progress`. The ticks committed
before are kept: they stay readable in `engine.results`, `engine.results.end_state` is set, the
`on_error` callbacks observe the exception and it propagates to the caller. Nothing is evaluated
after it, and a later `replay(..., state=engine.results.end_state)` continues where it stopped.

## Results

`Results` is columnar. `Results.commit(chunk)` is the one way in: a `ResultChunk`
(`gemini/engine/chunks.py`) holds the ticks of one evaluation, whatever their number, one
included: `times`, `durations`, a `PathColumns` per module path and the per-tick `skips` and
`errors`. `PathColumns(present, columns)` has a boolean mask of the ticks the path was evaluated
for and one column per field, every column with one entry per tick (entries of absent ticks are
ignored). A column is a NumPy array or, for objects such as list outputs and message strings, a
Python list; `PathColumns.of(result, health, present)` takes them from a leaf `ModuleResult` and
a `Health` of arrays or scalars (scalars broadcast) and computes `operating` from the flows.
Columns are kept by reference; a declared `X | None` float output with NaN becomes a list with
`None`. A chunk of one tick is the same code as a window. Chunks are concatenated lazily in `to_frame`, which gives the
columns and dtypes a table built row by row would have: columns in the order of first appearance
(paths by the first tick they are present, then as given), a typed array that is present
everywhere keeps its dtype, floats with an absent tick are `float64` with NaN, and every other
column (booleans or integers with an absent tick, lists, strings, `None`) is read as pandas reads
a column of row values with NaN for absent ones. Energy fields and `operating` are computed from
the columns.

The ports of a leaf are columns too, by `Stream.quantities()`: `<port>.<quantity>` for a fluid
(`results.get("hp", "hot_out.enthalpy_flow")`) and the port's name for a `Power`
(`results.get("grid", "power_out")`); the quantities are listed in [types.md](types.md). A limit
of `gm.checks.Limits` may name one, and `gm.kpi`, `gm.economics` and the energy report read them.

`Results[path]` returns the series of one module path; `Results[path].field` is a pandas Series
and an unknown path or field raises `ValidationError`. Only leaf results are stored: twins in
replay and the leaves of the plant call in simulation, not root or composite formula outputs.
`Results[path].get(field, unit=...)` converts only the six fields of `SERIES_UNITS` (`head`,
`pressure_drop`, `discharge_pressure`, `power`, `duty`, `thermal_power`), because a conversion
needs the quantity of a difference, which results do not store; other fields raise `ValueError`.
`SERIES_UNITS` therefore stays; it is not the unit table of the JSON views below.

**Units.** Every field states its SI unit. `results.units` is `{path: {field: unit}}`, taken from
the plant's output declarations when a run starts (`declared_units`); a field without a declared
unit (`operating`, the `health_*` fields, text outputs) is dimensionless, `"-"`. The table is saved
with the results.

**JSON views.** Every public return passes `gemini.utils.jsonable.to_plain`: NaN and infinity
are `null`, times are ISO 8601 UTC text. Every view takes `units`, a map from quantity to unit
([output units](api.md#output-units)), and `results.quantities` is `{path: {field: quantity}}`, saved
with the results; a field without a quantity is left alone.

| Call | Returns |
|---|---|
| `names()` | `{path: [field, ...]}` of everything `get` reads, in column order |
| `get(path, field, start=None, end=None)` | `{time: [...], values: [...], unit}`; the window is inclusive |
| `summary(path=None, start=None, end=None)` | `{path: {field: {min, max, mean, unit}}}` of the numeric fields |
| `errors()` | rows `{timestamp, module, code, type, message}`, oldest first: failed rows and skipped rows (`missing_value`) |
| `to_dict()` | `{time, duration, series: {path: {field: {unit, values}}}, errors, skip_counts, end_state}` |

`to_frame(units=None, table="series")` is the one route to a DataFrame. `"series"` returns a copy
with one column per field, named `path.field` (a root field by its own name; these are the
calculated-tag names), the dtypes a table built row by row has and the unit of each column in
`attrs["units"]`. `"energy"` returns the table of `energy_report`: energy per output, peaks,
operating hours, alarms, skips and errors, which `repr(results)` prints. `skip_counts` holds the skips per path and
reason, and `failures` the rows where a module raised (the part of `errors()` that is not a
skip; `EventLog` logs these).

**Files.** `save(path)` and `Results.load(path)` write and read one `.npz` file (the suffix is added
when missing); `to_bytes()` and `Results.from_bytes(data)` do the same without a file path.
`gemini/engine/archive.py` writes a float, integer or boolean column as that array and any
other column (lists, strings, `None`, mixed cells) as one JSON text with exact floats; the
metadata (units, durations, skips, failures, energy fields, end state) is one JSON text. Loading
uses `allow_pickle=False`, so no pickle is read, and gives the same bits, units and end state.
Anything that is not an archive of this format (including the former Parquet and CSV files)
raises `ValidationError` with the code `invalid_format`. The metadata records `gm.__version__`, and a
file written before 0.1.0 raises `ValidationError` with the code `old_format`, as a checkpoint
written before 0.2.0 does: it holds a plant dict of an older form.
Checkpoints keep their results in the same file.

**End state.** `results.end_state` is plain JSON `{position, module_states}`: the last committed
tick (ISO text or `null`) and the state tree of each stateful twin (`{path: tree}`; in a
simulation `{"": tree}`). It is set at the end of every run, also of a cancelled or failed one,
survives `save` and `to_bytes`, and is the input of `replay(..., state=...)`: stateful modules
continue from it and ticks up to its position are not evaluated again, so
`replay(data, end=t)` followed by `replay(data, state=first.end_state)` gives the numbers of one
`replay(data)`, in any engine built for a plant of the same shape. A state that is not of this
shape, or names a module the plant lacks, raises `ValidationError`.

## Checkpoints

The JSON manifest stores the `gm.__version__` that wrote it, the run kind, the importable plant class, `plant.to_dict()`,
module states, the finite clock, the completed position, the original dataset fingerprint
(informational only), selected `only` paths, the error policy, the runtime settings captured at
run start, the backend, the creation time and sibling filenames. Results and unfinished replay/simulation rows
are written first, then the manifest is atomically replaced. The stored rows start `max_gap`
before the position, because a held previous row may still supply the next ticks; they use
JSON-encoded CSV cells to preserve exact float bits, and their JSON sidecar records the column
units and the run's `max_gap`, which a resumed run reuses. A checkpoint never depends on the file
or service that originally supplied data.

`Engine.load_checkpoint(path, callbacks=None)` rebuilds the plant from the manifest and restores
the run state with the saved backend and error policy. `save_checkpoint(path)` also works before
the first run; the checkpoint then holds the plant and no results. `resume()` continues strictly after the saved
position, or returns the stored results when the clock is finished; a resumed run gives the same
results as an uninterrupted one. Resume and live calls re-apply the saved precision and display
units, but not the default fluid, which only seeds newly built modules and streams.

## Live runs

`live` evaluates the engine's plant. Without `checkpoint` the engine continues from its own committed
position, so two calls on one engine process every tick once and write no file. An existing live checkpoint must have been saved for a plant
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
