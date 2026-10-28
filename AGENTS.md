# GEMINI Python package

GEMINI is TNO's geothermal digital-twin suite. Equipment and plants share a composable
`Module` contract with Pydantic v2 schemas, immutable SI streams, recursive parameters,
state snapshots and observer hooks. Preserve the captured numerical baseline.

## Layout

```text
gemini/
├── __init__.py    # curated import gemini as gm API
├── core/
│   ├── types/     # quantities, bindings/dates, Fluid, flows, Profile, results and Cost
│   ├── physics/   # SI correlations, conversions and fluid properties
│   ├── modules/   # Module, equipment, handwritten plants, catalogue and wiring observations
│   ├── config/    # portable PlantConfig, GEMINI import and load/save boundary
│   ├── data/      # Dataset, Loader and existing drivers under drivers/
│   └── engine/    # finite Clock, Engine, steps, Results, callbacks and checkpoints
├── optim/        # calibration through public Engine.replay
├── design/
└── agentic/
tests/             # mirrors core, optim, public API, golden cases and full-dataset e2e
examples/          # 00–12 executable examples, including complete quickstart and resume
datasets/geothermal_doublet/  # original project and converted plant.json
```

## Read before coding

- [Public API](.claude/docs/api.md)
- [Engine and checkpoints](.claude/docs/engine.md)
- [Data and sampling](.claude/docs/data.md)
- [Conventions](.claude/docs/conventions.md)
- [Core types](.claude/docs/types.md)
- [Writing modules](.claude/docs/modules.md)
- [Physics](.claude/docs/physics.md)
- [Testing](.claude/docs/testing.md)
- [Numerical decisions](.claude/docs/refactor-notes.md)

Retain the workspace dataset name `geothermal_doublet`. Work locally on `refactor/engine`,
commit completed phases, and do not push or open a PR. `core/modes` is removed; do not add
compatibility imports. Engine/optimizer calls accept the configured plant, never a separate
PlantConfig. No engine loop sleeps or schedules itself. Keep the public API small.
