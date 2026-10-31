# GEMINI Python package

GEMINI is a composable geothermal digital-twin package. Preserve captured numerical behaviour.

## Start here

Test with the development profile (`make test`); see
[Testing: Test profiles](.claude/docs/testing.md#test-profiles).

Physics lives in `gemini/physics/` or `gemini/modules/<category>/_physics.py`: a module declares and
wires, and calls physics functions. Helpers of the module package live in `gemini/modules/_utils/`.

Run a plant with `gm.simulate(plant, profile)`, `gm.replay`, `gm.live` and `gm.resume`; keep
`gm.Engine` for complex tasks ([functions or engine](.claude/docs/engine.md#functions-or-engine)).
`gm.schedule` plans the run input of a design from its demand
([schedule](.claude/docs/engine.md#schedule)).

Everything in the plant's energy and mass flow is a module, everything that crosses between modules
goes through a port, and a plant total is read from the ports of the modules at the plant's edge
([energy flow](.claude/docs/modules.md#energy-flow)). Check a run with `gm.checks.plant_balance`.

Every port of a module is connected or named as a plant port; there are no automatic plant ports
([plants](.claude/docs/plants.md#level-1-the-builder)). A composite may derive its children's values
by overriding `set_params`
([modules](.claude/docs/modules.md#a-composite-that-sets-its-childrens-values)).

Every public return uses one of three shapes, value, problem or check, built by
`gemini/types/shapes.py` ([return shapes](.claude/docs/api.md#return-shapes)). Every public call
raises by default; `on_error="record"` reports instead ([errors](.claude/docs/errors.md)).

Read every file in `.claude/docs/` before changing the repository:

- [Public API](.claude/docs/api.md): every frozen public name, its return shape and status; start
  here to use the package.
- [Plants](.claude/docs/plants.md): the builder, the spec, templates, dates and bindings.
- [Conventions](.claude/docs/conventions.md): dependencies, naming, comments and code quality.
- [Data](.claude/docs/data.md): in-memory datasets, sampling and gaps.
- [Engine](.claude/docs/engine.md): clocks, runs, callbacks, results, checkpoints and live.
- [Economics](.claude/docs/economics.md): economics, KPIs, checks and well analysis.
- [Equipment](.claude/docs/equipment.md): every shipped module, its model and energy audit.
- [Errors](.claude/docs/errors.md): the rule for raising, the seven `gm.errors` classes, the codes.
- [Glossary](.claude/docs/glossary.md): one name per concept for parameters, outputs and ports.
- [Legacy](.claude/docs/legacy.md): the old-format boundary and conversion rules.
- [Modules](.claude/docs/modules.md): declarations, listings, calls, outputs, hooks and state.
- [Native engine](.claude/docs/native-engine.md): the computation-graph design and its status.
- [Physics](.claude/docs/physics.md): every physics function by file, SI correlations and numerical
  constraints.
- [Refactor notes](.claude/docs/refactor-notes.md): retained numbers and known limitations.
- [Runtime](.claude/docs/runtime.md): context-local process settings.
- [Testing](.claude/docs/testing.md): tiers, test profiles, datasets, budgets, fixtures and CI.
- [Types](.claude/docs/types.md): streams, fluids, declarations, profiles and balances.
- [Utilities](.claude/docs/utils.md): the `gemini.utils` helpers and how to add one.

When a commit changes behaviour, structure or conventions, update the relevant document in the
same commit. The public API is frozen: a breaking change to a public name or return field raises the minor
number of `gm.__version__` ([freeze rule](.claude/docs/conventions.md#public-api-freeze)).

## Branching

Work directly on `refactor`: commit there and push `origin refactor`. Do not create another
branch unless the user explicitly asks for one, and open a pull request only when asked.

## Layout

```text
gemini/
├── __init__.py       # curated import gemini as gm API
├── utils/            # general helpers; the topic files are a leaf that imports nothing else from gemini
│   ├── data/         # in-memory Dataset and Loader only
│   └── legacy/       # all old-format I/O, tables and conversion
├── errors/           # the gm.errors classes and codes; leaf package that imports nothing else from gemini
├── backends/         # python (scalar) and numpy (array) implementations of the ops
│   └── runtime.py    # context-local precision, display units and default fluid
├── ops/              # op registry, dispatch, Constant, where and check used by physics
├── graph/            # Node, Graph, Proxy, Tracer, Interpreter, cache and runner
├── physics/          # shared formulas: SI correlations and unit conversions
├── types/            # quantities, streams, fluids, declarations, profiles, bindings, costs, return shapes
├── modules/          # Module base class, _utils/ helpers; one folder per category with its _physics.py
├── engine/           # Clock, run functions, Engine, steps, Results, callbacks, checkpoints
├── optim/            # calibration through Engine.replay
├── analysis/         # well performance and integrity, fits; kpi.py is the gm.kpi namespace
├── economics/        # capex, opex, levelised cost, CO2, cash flow
├── checks/           # balances and bounds over a finished run
├── testing/          # check_module for a new module class
└── profiles/         # demand profiles
docs/schemas/         # JSON Schemas and samples of the exchanged documents
examples/             # area/category/NN_name.py; shared plant and data in examples/shared/
scripts/              # test_changed.py, write_schemas.py, migrate_plants.py
tests/                # unit mirror, integration, e2e and immutable fixtures
```

Modules declare parameters and ports in `__init__`; `forward(self, inlets)` receives one
immutable `Ports` mapping while controls and boundaries are pre-applied and read from `self`. It
returns a fluid-outlet dictionary; leaf `_compute_outputs(self, inlets, outlets)` methods and
composite output formulas run automatically afterward. Pre-hooks receive `(module, inlets)` and
forward hooks receive `(module, inlets, outlets)`. Plants are built from data
([plants.md](.claude/docs/plants.md)) and own persistence, bindings, and dated design. `gemini.utils.data` is in-memory only. No engine loop sleeps or schedules itself. Keep the public
API small and examples outside the package. Details are in
[conventions.md](.claude/docs/conventions.md) and [modules.md](.claude/docs/modules.md).
