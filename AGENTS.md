# GEMINI Python package

GEMINI is a composable geothermal digital-twin package. Preserve captured numerical behaviour.

## Start here

Test with the development profile (`make test`); see
[Testing: Test profiles](.claude/docs/testing.md#test-profiles).

A leaf module computes and a plant connects; no class does both
([modules](.claude/docs/modules.md), [plants](.claude/docs/plants.md)). A leaf has physics calls and
one method, `forward`. Every composite is a `Plant`: it declares children, ports and connections in
`__init__` and never writes `forward`. The engine closes loops and solves constraints.

Physics lives in `gemini/physics/` or `gemini/modules/<category>/_physics.py`: a module declares and
calls physics functions. `gemini/modules/` holds `Module`, `Plant`, `ModuleList` and
`ModuleDict`; machinery goes in an `_utils/` folder, code of one category in a private file of its
folder, and `gemini/modules/plants/` holds only plant classes
([where a file goes](.claude/docs/conventions.md#module-rules)).

Learn the package from [examples/README.md](examples/README.md): quickstart, basics 01 to 06, any
recipe, then the cases. gemini holds no data file: plants are Python classes, and JSON is only the
plant dict agents use (`gm.plants.from_dict`, `plant.to_dict`, `gm.plants.schema`). Data lives in
`inputs/`, never `examples/`, and is not installed ([data](.claude/docs/data.md#where-data-lives)).

Run a plant with `gm.simulate(plant, profile)`, `gm.replay`, `gm.live` and `gm.resume`; keep
`gm.Engine` for complex tasks ([functions or engine](.claude/docs/engine.md#functions-or-engine)).
`gm.schedule` plans the run input of a design from its demand, with outage days from
`operating_days` and the role of each unit read from the wiring
([schedule](.claude/docs/engine.md#schedule)). `gm.challenge_rules()` and `gm.profiles.demand()` are
the challenge's, and `gm.plants.example("HeatingCoolingPlant")` runs that year with every requirement
checked (`examples/cases/challenge_year.py`).

Everything in the plant's energy and mass flow is a module, everything that crosses between modules
goes through a port, and a plant total is read from the ports of the modules at the plant's edge
([energy flow](.claude/docs/modules.md#energy-flow)). Check a run with `gm.checks.plant_balance`.

Every port of a module is connected or named as a plant port; there are no automatic plant ports
([plants](.claude/docs/plants.md#the-builder)). What a design holds beside its parameters, such as a
setpoint, is set with `plant.set_inputs` and stored in the plant dict under `inputs`. A plant may derive its children's values by
overriding `set_params`
([modules](.claude/docs/modules.md#a-plant-that-sets-its-childrens-values)).

Every public return uses one of three shapes, value, problem or check, built by
`gemini/types/shapes.py` ([return shapes](.claude/docs/api.md#return-shapes)). Every public call
raises by default; `on_error="record"` reports instead ([errors](.claude/docs/errors.md)).

Read every file in `.claude/docs/` before changing the repository:

- [Public API](.claude/docs/api.md): every frozen public name, its return shape and status; start
  here to use the package.
- [Plants](.claude/docs/plants.md): plant classes, the builder, the plant dict, loops, constraints,
  outputs, dates and bindings.
- [Conventions](.claude/docs/conventions.md): dependencies, naming, comments and code quality.
- [Data](.claude/docs/data.md): in-memory datasets, sampling, gaps and where data lives.
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
├── modules/          # module.py, plant.py, container.py, _utils/; one folder per category with its _physics.py
│   └── plants/       # plant classes only; _utils/ holds the plant tools
├── engine/           # Clock, run functions, Engine, steps, Results, callbacks, checkpoints
├── optim/            # calibration through Engine.replay, minimize and sample through gm.simulate
├── analysis/         # well performance and integrity, fits, schedule, roles; kpi.py is gm.kpi
├── economics/        # capex, opex, annualised and levelised cost, LCTS, CO2, cash flow
├── checks/           # balances and bounds over a finished run
├── testing/          # check_module for a new module class
└── profiles/         # demand profiles
docs/schemas/         # generated JSON Schemas and samples of the exchanged documents
inputs/               # not installed: hackathon/, plants/ (example values), doublet_heat/, legacy_project/
examples/             # quickstart.py, basics/, recipes/, cases/, scripts only
scripts/              # test_changed.py, write_schemas.py
docker/               # sandbox.Dockerfile, the image of a module sandbox (make sandbox-image)
tests/                # unit mirror, integration, e2e (expected/ holds example outputs), fixtures
```

Modules declare parameters and ports in `__init__`; `forward(self, inlets)` receives one
immutable `Ports` mapping while controls and boundaries are pre-applied and read from `self`. A leaf
assigns its outputs there and returns a dictionary of outlets; the combinations of a plant run
automatically afterward. Pre-hooks receive `(module, inlets)` and forward hooks receive
`(module, inlets, outlets)`. Plants ([plants.md](.claude/docs/plants.md)) own persistence, bindings,
and dated design. `gemini.utils.data` is in-memory only. No engine loop sleeps or schedules itself.
Keep the public
API small and examples outside the package. Details are in
[conventions.md](.claude/docs/conventions.md) and [modules.md](.claude/docs/modules.md).
