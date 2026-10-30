# Native engine: computation graph design

Status: agreed design (2026-10-29). Nothing is implemented yet. First step is the ESP prototype
(`native-engine-start.md`).

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
