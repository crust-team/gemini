# GEMINI Python package

GEMINI is TNO's geothermal digital-twin suite. Equipment and plants share a composable
`Module` contract with Pydantic v2 schemas, immutable SI streams, recursive parameters,
state snapshots and observer hooks. Preserve the captured numerical baseline.

## Layout

```text
gemini/
├── core/
│   ├── base/       # Stream and Health
│   ├── physics/    # SI correlations, conversions and fluid properties
│   ├── modules/    # Module, Sequential, GraphPlant and equipment categories
│   ├── config/     # dated schemas, GEMINI import and graph construction
│   ├── data/       # database drivers and CSV time series
│   ├── engine/     # discovery, Results and EventLog
│   └── modes/      # twin, history, live and scenario
├── design/
├── optim/
└── agentic/
tests/              # mirrors core; immutable golden cases and full-dataset e2e
examples/           # nine executable examples
datasets/geothermal_doublet/  # original project and converted plant.json
```

## Read before coding

- [Conventions](.claude/docs/conventions.md)
- [Writing modules](.claude/docs/modules.md)
- [Physics](.claude/docs/physics.md)
- [Testing](.claude/docs/testing.md)
- [Numerical decisions](.claude/docs/refactor-notes.md)

The example folder was renamed to `geothermal_doublet` in the workspace; retain that name.
Work locally on `refactor/modules`, commit completed phases, and do not push or open a PR.
