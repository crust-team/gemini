# GEMINI Python package

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
│   └── engine/       # Clock, Engine, steps, Results, callbacks, checkpoints
├── legacy/           # all old-format I/O, tables and conversion
├── optim/            # calibration through Engine.replay
├── design/
└── agentic/
examples/             # package/category/NN_name.py; shared plant/data outside package
tests/                # unit mirror, integration, e2e and immutable fixtures
```

## Read before coding

- [Public API](.claude/docs/api.md)
- [Engine and checkpoints](.claude/docs/engine.md)
- [Data and sampling](.claude/docs/data.md)
- [Legacy bridge](.claude/docs/legacy.md)
- [Conventions](.claude/docs/conventions.md)
- [Core types](.claude/docs/types.md)
- [Writing modules](.claude/docs/modules.md)
- [Physics](.claude/docs/physics.md)
- [Testing](.claude/docs/testing.md)
- [Numerical decisions](.claude/docs/refactor-notes.md)
- [Runtime settings](.claude/docs/runtime.md)

Work locally; do not push or open a PR. Modules declare parameters and ports in `__init__`, use
plain `forward` arguments, assign outputs and return outlets. `core.config`, data drivers, and run
modes are removed. Plants own persistence, bindings, and dated design. Core data is in-memory
only. No engine loop sleeps or schedules itself. Keep the public API small and examples outside
the package.
