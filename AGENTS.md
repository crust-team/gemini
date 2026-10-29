# GEMINI Python package

## Start here

Read every file in `.claude/docs/` before changing the repository:

- [Public API](.claude/docs/api.md): curated imports and supported user workflows.
- [Conventions](.claude/docs/conventions.md): dependencies, style and module contracts.
- [Data](.claude/docs/data.md): in-memory datasets, sampling and gaps.
- [Engine](.claude/docs/engine.md): replay, simulation, live runs and checkpoints.
- [Legacy](.claude/docs/legacy.md): the old-format boundary and conversion rules.
- [Modules](.claude/docs/modules.md): declarations, forwarding, outputs and hooks.
- [Physics](.claude/docs/physics.md): SI correlations and numerical constraints.
- [Refactor notes](.claude/docs/refactor-notes.md): retained numbers and known limitations.
- [Runtime](.claude/docs/runtime.md): context-local process settings.
- [Testing](.claude/docs/testing.md): tiers, datasets, budgets, fixtures and CI.
- [Types](.claude/docs/types.md): streams, fluids, declarations, profiles and balances.

When a commit changes behaviour, structure or conventions, update the relevant document in the
same commit.

GEMINI is a composable geothermal digital-twin package. Preserve captured numerical behavior.

## Layout

```text
gemini/
├── __init__.py       # curated import gemini as gm API
├── core/
│   ├── types/        # quantities, flows, profiles, bindings and dated params
│   ├── physics/      # SI correlations and unit conversions
│   ├── modules/      # equipment and generic handwritten plants
│   ├── data/         # in-memory Dataset and Loader only
│   ├── engine/       # Clock, Engine, steps, Results, callbacks, checkpoints
│   └── legacy/       # all old-format I/O, tables and conversion
├── optim/            # calibration through Engine.replay
├── design/
└── agentic/
examples/             # package/category/NN_name.py; shared plant/data outside package
tests/                # unit mirror, integration, e2e and immutable fixtures
```

Work locally; do not push or open a PR. Modules declare parameters and ports in `__init__`;
`forward(self, inlets)` receives one immutable `Ports` mapping while controls and boundaries are
pre-applied and read from `self`. It returns a fluid-outlet dictionary; leaf
`_compute_outputs(self, inlets, outlets)` methods and composite output formulas run automatically
afterward. Pre-hooks receive `(module, inlets)` and forward hooks receive
`(module, inlets, outlets)`. `core.config`, data drivers, and run
modes are removed. Plants own persistence, bindings, and dated design. Core data is in-memory
only. No engine loop sleeps or schedules itself. Keep the public API small and examples outside
the package.
