# GEMINI Python package

GEMINI is a composable geothermal digital-twin package. Preserve captured numerical behaviour.

## Start here

Test with the development profile (`make test`); see
[Testing: Test profiles](.claude/docs/testing.md#test-profiles).

Read every file in `.claude/docs/` before changing the repository:

- [Public API](.claude/docs/api.md): curated imports and supported user workflows.
- [Conventions](.claude/docs/conventions.md): dependencies, naming, comments and code quality.
- [Data](.claude/docs/data.md): in-memory datasets, sampling and gaps.
- [Engine](.claude/docs/engine.md): clocks, runs, callbacks, results, checkpoints and live.
- [Equipment](.claude/docs/equipment.md): every shipped module, its model and energy audit.
- [Errors](.claude/docs/errors.md): the `gm.errors` classes and when each is raised.
- [Legacy](.claude/docs/legacy.md): the old-format boundary and conversion rules.
- [Modules](.claude/docs/modules.md): declarations, listings, calls, outputs, hooks and state.
- [Native engine](.claude/docs/native-engine.md): the computation-graph design and its status.
- [Physics](.claude/docs/physics.md): SI correlations and numerical constraints.
- [Refactor notes](.claude/docs/refactor-notes.md): retained numbers and known limitations.
- [Runtime](.claude/docs/runtime.md): context-local process settings.
- [Testing](.claude/docs/testing.md): tiers, test profiles, datasets, budgets, fixtures and CI.
- [Types](.claude/docs/types.md): streams, fluids, declarations, profiles and balances.
- [Utilities](.claude/docs/utils.md): the `gemini.utils` helpers and how to add one.

When a commit changes behaviour, structure or conventions, update the relevant document in the
same commit.

## Branching

Work directly on `refactor`: commit there and push `origin refactor`. Do not create another
branch unless the user explicitly asks for one, and open a pull request only when asked.

## Layout

```text
gemini/
├── __init__.py       # curated import gemini as gm API
├── utils/            # general helpers; leaf package that imports nothing else from gemini
├── errors/           # every gm.errors class; leaf package that imports nothing else from gemini
├── core/
│   ├── physics/      # SI correlations and unit conversions
│   ├── types/        # quantities, streams, fluids, declarations, profiles, bindings, costs
│   ├── runtime.py    # context-local precision, display units and default fluid
│   ├── modules/      # Module base class, equipment, containers and the Doublet plant
│   ├── data/         # in-memory Dataset and Loader only
│   ├── engine/       # Clock, Engine, steps, Results, callbacks, checkpoints
│   └── legacy/       # all old-format I/O, tables and conversion
└── optim/            # calibration through Engine.replay
examples/             # area/category/NN_name.py; shared plant and data in examples/shared/
scripts/              # test_changed.py, the development test profile
tests/                # unit mirror, integration, e2e and immutable fixtures
```

Modules declare parameters and ports in `__init__`; `forward(self, inlets)` receives one
immutable `Ports` mapping while controls and boundaries are pre-applied and read from `self`. It
returns a fluid-outlet dictionary; leaf `_compute_outputs(self, inlets, outlets)` methods and
composite output formulas run automatically afterward. Pre-hooks receive `(module, inlets)` and
forward hooks receive `(module, inlets, outlets)`. Plants own persistence, bindings, and dated
design. Core data is in-memory only. No engine loop sleeps or schedules itself. Keep the public
API small and examples outside the package. Details are in
[conventions.md](.claude/docs/conventions.md) and [modules.md](.claude/docs/modules.md).
