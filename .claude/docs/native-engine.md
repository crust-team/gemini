# Native engine: computation graph design

Status: agreed design (2026-10-29). All physics and leaves are written with ops and replay runs
through the graph by default. Sections 1 to 11 are the design as agreed; section 12 records where
the implementation differs and why, and section 13 how composites and replay work.

## 1. Why

Profiling `examples/doublet_heat` (one-month replay, 2976 ticks, 8 twins, 9.7 s) showed physics
is only 6.5 % of the time; about 90 % is framework overhead per tick (`Module` 22 %, `difflib`
15 %, engine/results 10 %, types 10 %, pydantic 4 %). The win is changing the execution model from
"one tick at a time" to "the whole time range at once", via a traced computation graph. The graph
also enables batched scenarios (uncertainty, optimisation), gradients later (calibration,
sensitivity), unit checks before running, and a readable plant graph for the agent.

The public API (`Engine`, `Results`, `Dataset`) does not change for the user.

## 2. Pipeline

```
physics and modules in Python, written with gm ops (gm.log, gm.where, gm.check, ...)
        |  trace with Proxy (one trace per Module)
        v
graph (IR): typed nodes, inputs, outputs
        |  passes: unit check (now); fusion, masking of expensive branches (later)
        v
interpreter -> backend: python | numpy | numba (later) | C++ (later)
```

- Capture: Proxy tracing (symbolic trace). No bytecode capture.
- Granularity: each Module is traced on its own; the Engine links module graphs through the
  plant connections. A module that cannot be traced runs in plain Python on its own
  (graph break), the rest stays in the graph.
- Shapes: the IR is multi-dimensional from day one (scenario x time). Only the time dimension is
  implemented first.
- Cache: graphs are cached and re-traced only when the plant structure, a module, or input
  types change (guards).
- Autodiff: not implemented; the IR must allow adding it later. GPU: out of scope, IR must not
  block it.

## 3. Op kinds

Every op declares its kind. The kind is what later passes (fusion, masking) rely on.

| kind | examples | numpy mapping |
|---|---|---|
| elementwise | add, sub, mul, div, pow, neg, abs, exp, log, log10, sqrt, trig, comparisons, logical ops, where, maximum, minimum, clip | direct `np.*` |
| reduction | sum, mean, max, min, cumsum, trapezoid | direct `np.*` |
| interp | 1-D table interpolation; N-D interpolation | `np.interp`; SciPy for N-D |
| check | validity checks producing per-row error codes | small own code |
| solver | newton, brentq (per-element stopping) | `scipy.optimize.newton` (array), `scipy.optimize.elementwise.find_root` |
| scan | time-stepping with carried state (stateful modules, time integrals, ODEs) | defined only; runs through a Python fallback loop for now |

Fusion (merging chains of elementwise ops into one loop) is postponed. The op kinds keep the
door open. Likely later route: a Numba backend (fusion and scan as compiled loops), then measure,
then decide on C++.

## 4. Graph inputs: roles

Three roles, separate from data types (a data type says what a value is; a role says how the
engine treats it):

| role | meaning | examples |
|---|---|---|
| `Parameter` | calibratable | pump curve coefficients, number of stages, empirical correlation coefficients |
| `Constant` | fixed by default, can be released for sensitivity analysis | gravity, gas constant, reference heat capacity |
| `State` | carried from step to step by scan | storage tank temperature |

- Parameters and Constants are named graph inputs, never baked-in numbers, so calibration and
  scenario batches reuse one graph. Giving a parameter a scenario dimension makes Monte Carlo
  over parameters free.
- Only pure math and unit-conversion numbers (2, 60, pi, bar->Pa) are literals in the graph.
- Physical constants are defined once as `Constant` in `gemini/core/physics/constants.py` and
  shared; the tracer creates one graph input per constant.
- Declared in modules by attribute assignment (`self.stages = gm.Parameter("50")`); `Module`
  registers them; `named_parameters`, `named_constants`, `named_states` list them.
- Defined in `gemini/core/modules/parameter.py`, next to `Module`. Reuse and extend whatever
  parameter mechanism already exists.

## 5. Units and types

- Units are converted to SI at the graph boundary. Inside the IR there are only SI numbers; the
  unit is kept as metadata on each node for the unit-check pass.
- dtypes: float64 for values, bool for conditions, integer for error codes. Nothing else for now.
- pydantic is removed from the package. Types become plain dataclasses (with slots); validation
  runs only at the boundary (user construction, config loading) and raises `gm.errors`. No
  validation in the hot path or during tracing.

## 6. Branches and errors (user sees only gm.where and gm.check)

Physics authors write:

```
if re < 2300: f = 64 / re            ->  f = gm.where(re < 2300, 64 / re, turbulent(re))
if p < 0: raise PhysicsRangeError    ->  gm.check(p >= 0, PhysicsRangeError, "...")
```

The engine handles the side effects of evaluating both branches of `where` on arrays:

1. NaN / overflow warnings from the unselected branch are silenced inside the backend.
2. `check` does not raise immediately. It produces a per-row error code that travels with the
   value; `where` selects the error code from the chosen branch together with the value. Only
   errors that reach a graph output are raised. Python rebuilds the same `gm.errors` class and
   message. `on_error="raise"` raises the first failing row.
3. Expensive branches (for example a solver inside one branch) are later masked automatically by
   a graph pass, so they run only on their own rows. This is an engine decision, not the user's.

Every node keeps the Python file and line that created it, so errors from any backend point to
the physics line.

## 7. Backends

- `Backend` base class with one method per op; `gm.backends.register(...)`;
  `gm.runtime.settings(backend=...)`; automatic choice from input type, manual override possible.
- Fallback: an op missing in a backend runs on numpy.
- `python` backend: scalars with `math` — the current pure-Python path. It stays as the debug
  path, the test reference, and the path for platforms without wheels.
- `numpy` backend: arrays with NumPy and SciPy. Default until something faster exists.
- Order: python + numpy -> numba -> measure -> C++.
- Numerical equality: documented relative tolerance (for example 1e-12), not bit-exact. Golden
  tests unchanged.

## 8. Readable graph

`gm.explain` (and a text/JSON dump of the graph) with module names, parameters, constants and
units, for debugging and for the agent to explain where a number comes from.

## 9. Outputs, hooks and callbacks

Nothing that computes outputs today is lost; the user does not mark anything in the common case.

- **Output declarations** (all in `__init__`): leaves compute outputs in `_compute_outputs`
  (per-output compute methods may come later). Composites use `Output.of(self.child.output)` and
  `Output.ratio(self.a, self.b)` with direct references, not strings. Additive semantic types
  (`Electricity`, `HeatLoss`, `HeatSupplied`, `HeatAbsorbed`, `HeatAccumulation`, mass flow) are
  summed automatically: a composite that declares `Output(Electricity)` without a formula gets
  the sum over its descendants by name and type; `Output.total` is gone.
- **`_compute_outputs` and formula outputs** (`Output.of`, automatic sums, `Output.ratio`) are
  part of the module call, not hooks. They are traced together with `forward`, in the same
  fixed order (`forward` -> `_compute_outputs` -> formula outputs -> forward hooks ->
  `_check_outputs`), and become part of the module graph. `_check_outputs` runs once at trace
  time (every declared output must get a value). `gm.no_outputs()` traces a graph without the
  output step.
- **Forward hooks** are traced too, after the formula outputs. Hooks always return None, so the
  engine looks at what a hook does during the trace:
  - it writes outputs with `gm` ops -> it goes into the graph;
  - it only reads -> it is an observer, replayed per row from the results after the run;
  - it cannot be traced and writes outputs -> **only its module** runs in plain Python tick by
    tick (graph break); the rest of the plant stays in the graph.
- Pre-hooks follow the same rules.
- `gm.explain` lists every graph break and why.
- **Engine callbacks** observe by default and are replayed from the results after the run
  (`EventLog` and `AutoCheckpoint` are rebuilt from results the same way).
- A callback that must **change the run** (early stop, control logic) declares it. The engine
  then runs the range in chunks (for example one day) and calls it between chunks, so the graph
  is still used inside each chunk.

## 10. Package layout

```
gemini/
  ops/
    __init__.py      gm.log, gm.where, gm.check, ...
    registry.py      op registration: name, kind, signature
    math.py          arithmetic, exp/log/pow, trig
    logic.py         comparisons, where, maximum/minimum, clip
    reduce.py        sum, mean, cumsum
    interp.py        table interpolation
    check.py         check and per-row error codes
    solvers.py       newton, brentq
    control.py       scan (definition only for now)
  graph/
    node.py, graph.py, proxy.py, tracer.py, interpreter.py, cache.py
    passes/          units.py now; fusion.py later
  backends/
    base.py          Backend, register, settings
    python.py        scalar, math module
    numpy.py         arrays, NumPy and SciPy
  core/modules/
    parameter.py     Parameter, Constant, State
native/              C++ sources and ops.yaml, later, outside the Python package
```

`ops` only describes ops (name, kind, signature); implementations live in the backends, so a new
backend is one new file.

## 11. Later C++ decisions (already agreed, not started)

C++20, scikit-build-core + CMake, pybind11, cibuildwheel on manylinux_2_28 (x86_64, aarch64),
macOS, Windows; OpenMP `parallel_for` with bundled libomp; `Vectorized<T>`-style SIMD with
runtime CPU dispatch and Sleef; `ops.yaml` + codegen; googletest, per-op automatic tests, Google
Benchmark, sanitizers; lintrunner. Precompiled kernels first, code generation later as another
backend. Solvers as dedicated ops with per-element stopping.

## 12. Prototype status (ESP)

Implemented for one leaf module, the ESP, and everything its call needs:

- `gemini/backends`: `Backend`, `register`, `get`, `settings(backend=...)`, `select` (NumPy for
  array operands, Python for scalars) and `implementation` (NumPy fallback for a missing op);
  `python.py` and `numpy.py` with the ops the ESP uses plus `where` and `check`.
- `gemini/ops`: the registry (name, kind, arity), `dispatch`, `Operators`, `Constant`,
  `where`, `check`, `logical_and`, comparisons, arithmetic, `getitem` and the `scan` definition.
- `gemini/graph`: `Node` (op, kind, operands, name, role, unit, shape, source line, guards),
  `Graph` (inputs by role, outputs, checks, constants, outlet fluids, observers,
  `describe()`), `Proxy`, `Tracer` (one leaf module), `Interpreter` (value pass, then error
  pass), `GraphCache` (guards) and `run` (one traced call over arrays, or untraced calls per
  row on a graph break, then observer replay).
- `core/modules/parameter.py` re-exports the roles; the ESP constants are `Constant`s; the
  ESP is written with `ops.check`, `ops.where` and `ops.logical_and`; `Stream` is one
  slots dataclass used on every path.
- The traced ESP on NumPy equals the untraced ESP exactly on the July data (tolerance 1e-12,
  `tests/integration/test_graph_esp.py`) and is about 390 times faster
  (`scripts/benchmark_esp.py`).

Where the implementation differs from sections 1 to 11, and why:

- **Names are not public.** The ops are `gemini.ops.where`, `gemini.ops.check`, ... and the
  backend setting is `gemini.backends.settings(backend=...)`, not `gm.where` or
  `gm.runtime.settings(backend=...)`: the curated `gm` names are pinned and the public API is
  unchanged, and `core.runtime` sits above the backends in the dependency order.
- **`where` branches are plain values; the ops never raise.** Physics authors write
  `where(condition, a, b)` and both branches are always evaluated. On the Python backend
  `truediv`, `pow`, `log`, `sqrt`, `exp`, `mod`, `floordiv` and the other ops return `inf` or `nan`
  silently, like NumPy, for division by zero, a negative logarithm or overflow. One thing cannot be
  hidden: `/` and `**` on two plain Python floats raise before any op runs, so a division or power
  that can be invalid in an unselected branch is written `ops.truediv(a, b)` or `ops.pow(a, b)`.
- **Eager calls and branch-aware checks.** A direct call is the same `forward` and ops on the
  Python backend, inside a scope (`gemini/ops/scope.py`), with no graph. Entering the outermost scope
  sets `np.errstate(all="ignore")` and gives exact floats as `np.float64`, so plain `/` and `**` are
  silent; leaving converts to `float` and `bool`. A failing `ops.check` on concrete scalars raises a
  marked error, which `@ops.physics` returns as a `Failed` value at the function boundary; `where`
  drops the unselected branch's `Failed` and an op over two keeps the earlier. In a trace the rule is
  the same: **a check guards all results of its physics function** (reaching outer functions through
  data) and a check outside any physics function, which raises at once on an eager call, guards
  every output. This replaces "the error travels with the values named in the check"; `check`'s
  values only fill the message, a `str.format` template with the failing row's values. Float32
  is honoured by the ESP alone (`Module._scalar_mode`), which keeps `ops.truediv(head, power)`: an
  `np.float64` is not weak under NEP 50, so its float32 call runs unwrapped. The scope costs an
  eager ESP call about 40 % more CPU; replay does not use it.
- **Solvers.** `ops.brentq` and `ops.newton` (kind `solver`) record one node whose operands are
  the bounds or start plus `args` and whose attributes hold the function and settings. The
  function is module-level, written with ops, takes no traced closure and holds no check that
  can fail on some row; the interpreter calls it with concrete arrays. A failing solve returns NaN
  instead of raising, followed by a `where` and a `check` with the old message. The Python backend
  is `scipy.optimize.brentq` and the handwritten Newton loop. **The NumPy backend is not the
  SciPy routines of section 3**: `gemini/backends/solvers.py` repeats the scalar iterations step
  for step with an active-row mask. `find_root` lands up to 1.4e-12 relative from the Python
  result (Brent's own error is within `xtol`, so no setting meets 1e-12) and array
  `scipy.optimize.newton` returns a different iterate, which moved the rounded NORSOK pH on 34 %
  of random rows. The vectorised versions give the same iterates: measured worst relative differences are
  6.4e-16 (`dew_point`, earlier grid; 3.1e-16 on the latest), 2.2e-16 (NORSOK pH) and 0
  (`doublet_cold_fraction`). CSE never merges solvers.
- **A value-dependent `break`** becomes a fixed number of passes with a finished mask (`IceStorage`).
- **A result used only for its validity** (`FlashTurbine.forward`) goes through `ops.require`,
  or its error is dropped on every backend: errors travel with values, and nothing reads this one.
- **A physics function given a `Failed` returns it**, so the earliest failure wins as in a graph.
- **Integers** are `np.int64` in an eager call, so an integer argument divides like a float and
  still prints, indexes and loops as an int. Ints beyond 64 bits stay Python ints.
- **A solver's function may hold a check** when its bracket keeps it inside the valid range
  (`dew_point` passes a degenerate bracket for an out-of-range row).
- **Discrete choices and error rewraps.** A string-valued choice decided by values becomes an
  integer code selected by `where` (the Beggs-Brill regime). A `try` around a physics call cannot
  work in a trace, so the physics function takes the `error` class (`ramey_time_function`).
- **`ops.interp` is not bit-identical** to `a + (x - xl) * (b - a) / (xu - xl)`, so the NORSOK `Kt`
  table folds `where`s in the order of the old search. `ops.pow` gives NaN where Python gave a
  complex number, so a check on a complex result is `not isnan`.
- **An `index` op kind** (`getitem`) selects one item of a vector parameter such as a curve
  coefficient, on the last axis so a scenario axis can lead.
- **No `named_constants` or `named_states`.** A module's constants are known only by tracing
  its physics (`graph.by_role("constant")`); `states()` already lists states.
- **`Stream` and `FluidProperties` are plain slots dataclasses.** `StreamState` and the `rho_l`,
  `rho_g` and `gmf` graph inputs are gone. Validation happens at the boundary and raises
  `gm.errors`: numbers become `float`; `m_dot` must be finite, `T > 0`, `p >= 0`
  (`PhysicsRangeError`). When a field is an array or a traced value the same limits are
  `ops.check` calls, so an invalid row raises the same class. `with_` is a trusted copy
  (`object.__new__`, same `Fluid`, only changed fields checked), about 5 us against 25 us before.
  A traced inlet is a `Stream` of `Proxy` fields with the concrete `Fluid`: **a `Fluid` is static
  during a trace**, its property values are plain floats in the graph, not named inputs, and the
  module's own fluid and the inlet fluids are cache guards. This departs from section 4 for fluid
  properties: they are configuration selected by a guard, and it keeps two-phase branching on
  `gas_mass_fraction` structural. `Parameter(structural=True)` is read as a plain value in a
  trace and its value is a cache guard (`traced_shape` in `tracer.py`); use it for a numeric value
  that decides structure. `Declaration.schema` of a port is `{}`.
- **Units** are recorded on graph inputs only; the unit-check pass is not implemented.
- **Graph breaks** are stateful modules (no `scan` yet), modules with pre-hooks, float32 precision
  and any `TraceError` from Python control flow or conversions; section 13 says at which level.
  The Python solves `close_loop` and `plants/nodal.py` break their whole composite.
- **An unmarked hook runs once during the trace** on traced values (that is how a reading hook is
  told from a writing one), so anything an observer stores then is a `Proxy`; afterwards they
  are replayed per row. A hook that raises `TraceError` is a graph break even when it would
  only have read, because the trace cannot tell.
- **Common-subexpression elimination** (`gemini/graph/passes/cse.py`,
  `eliminate_common_subexpressions(graph)`, in place) runs once per trace in `GraphCache`;
  `GraphCache(optimize=False)` turns it off. It merges `elementwise`, `index` and `check` nodes
  with the same op, operands and attributes. A literal operand is its type and exact value (`1`,
  `1.0` and `True` differ; `0.0` and `-0.0` differ; NaN equals itself). Graph inputs are never
  merged. The ESP graph goes from 141 to 100 nodes (two polynomials instead of four) with
  bit-identical outputs. A merged node carries the union of its guards. Because the raised error
  is the lowest code over all outputs and `where` keeps only the selected branch's codes, two
  twins merge only if each one is certain (it reaches a graph output through operands that are
  not a `where` branch) or has no guards, so no error moves onto a `where` branch it did not
  belong to; guarded twins that stay below a `where` branch are kept apart. Twin checks merge,
  codes are renumbered in creation order so the lowest code still wins, and the `Proxy` message
  values follow the merged nodes. Cost is linear in the node count. Not done: commutative
  operands, `reduction`/`interp`/`solver`/`scan` nodes, and guarded twins inside one branch.

## 13. Composites and replay through the graph

- **Composites.** `Module._run` hands a call made while a trace runs (`_Call.trace`) to
  `Trace.child`. A child's controls, boundaries and numeric parameters are graph inputs named
  `<relative path>.<name>` (the root keeps plain names); a child called twice reuses them; supplied
  keywords win without validation. The `ModuleResult` of traced values joins the parent's
  `call_records`, so `Output.of`, automatic sums, `Output.ratio` (now `where(bottom == 0, None,
  truediv(top, bottom))`) and helpers such as `Doublet.produce()` work unchanged. Guards cover every
  module of the tree. This replaces section 2's "each Module is traced on its own".
- **Breaks.** A stateful, pre-hooked or untraceable *leaf* child becomes one `break` node after the
  graph is rolled back (`Graph.mark`, `Graph.rollback`). It runs `module(**row)` on the plain path
  per row; a stateful child starts from its initial states, as a call outside `Module.step` does.
  Outputs and outlet fields are `break_output` nodes; a failing row is NaN with an error code, and
  `run` re-raises the child's exception. Outlet fluids come from a probe of `forward`; a row with
  another fluid fails. A composite child that cannot be traced, or any child with a marked
  observer, breaks the whole root: its leaves' call records feed the parent, and observers replay
  for the root only. A list of traced values is a vector output, recorded as `name[i]` items.
- **Observers.** `gemini.utils.hooks.observer(fn)` marks a read-only hook. It is never called on
  traced values; on the root it goes to `graph.pre_observers` or `graph.observers` and `replay_row`
  replays it per row. `EventLog` marks both of its hooks.
- **Limits.** `Declaration.limits()` gives an `ops.check(..., DeclarationError)` for every traced
  control, boundary and output, attached to every output so a violated bound always fails the
  row, and the root inlets carry the `Stream` limits.
- **Engine: batch, then the tick loop commits.** `Engine._run` builds a `Batch` after `on_run_start`
  for `kind == "replay"` unless `gemini.graph.settings(traced=False)` is active. For each twin and
  each stretch of ticks with one parameter snapshot, `Loader.arrays()` gives the columns, converted
  with `units.si_conversion` and run through the cached graph (one `GraphCache` per `Engine`). A row
  is **claimed** when everything is present, finite (NaN only for declared `X | None`) and no check
  or break reaches an output; `Interpreter.evaluate` returns a failed-row mask. The unchanged tick
  loop then commits: a claimed row gives a `ModuleResult` of Python scalars and `health`; every
  other row runs `_evaluate_twin` at its tick. So there is one error path: skips, exact error
  messages, `StepError`, callbacks, `AutoCheckpoint` and `resume` come from the old code, and the
  batch can only ever skip work it is sure of. Stateful twins, float32, untraceable twins and runs
  with a twin below another twin are not batched (`engine.batch.reasons`). This replaces section
  9's chunked engine callbacks: nothing needs to declare it changes the run.
- **Not done.** `scan`, float32, `trial_outlets` and `close_loop` in a graph, the unit-check pass,
  `gm.explain`. `simulate` and `live` stay tick by tick.

Validation is off the hot path. `Declaration` builds one cheap check at construction that accepts
only an exact `float` inside its bounds, an exact `bool` or `str`, or `None` for an optional kind
and returns the value unchanged; everything else, including every failure, takes the unchanged
full path, so values, coercions and messages are the old ones by construction. Defaults are
validated once (`default_value()`). This keeps a cheap check on the untraced path rather than
moving validation to the first call, because a bad output at tick 500 must still be caught there.
Traced rows are validated by `graph/limits.py` and the claim rule. Validation was only about 4 % of
an untraced ESP call, so this gained about 8 % there and nothing on the replay.

Measured on the July dataset (2976 ticks, 8 twins, none with a graph break): the replay takes
1.07 s through the graph against 5.22 s on the old path, with identical frames; the ESP alone
1.6 ms against 425 ms; CSE takes the ESP graph from 151 to 109 nodes and its call from 2.3 to
1.6 ms. The graph evaluation is only about 5 % of the replay. The rest is the per-tick commit:
`ModuleResult` per claimed row 40 %, `health` 25 %, `Results.append` 14 %.

Known gap: fluid properties and published correlation coefficients stay inline in the graph, not
`Parameter` or `Constant` inputs, so a calibration or sensitivity run cannot reach them without a
retrace. Named physical constants and module-level model constants are `Constant`s.
