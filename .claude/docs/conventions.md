# Implementation conventions

Use the smallest clear implementation. Keep Python 3.11 compatibility, Black/isort formatting,
100-character lines and flake8 docstrings. Preserve numerical behaviour; intentional changes
need a `NOTE(refactor)`, a physical explanation and a regression check.

## Layout and dependencies

- `core.base`: immutable `Stream` and `Health`.
- `core.physics`: reusable numerical functions and SI conversion.
- `core.modules`: equipment, `Module`, `Sequential` and `GraphPlant`.
- `core.config`: Pydantic graph schemas, GEMINI import, bindings and snapshots.
- `core.data`: service drivers and time-series readers.
- `core.engine`: registry discovery, result tables and event hooks.
- `core.modes`: independent measured twins, historical calibration, live windows and scenarios.
- `design`, `optim`, `agentic`: reserved application namespaces.

Dependencies flow `core.physics` ← `core.modules` ← `core.config` / `core.modes`
← `design` / `optim` ← `agentic`. Equipment does not import configuration or data access.
Graphs may contain other graphs; equipment shares physics functions instead of importing
another equipment implementation. Discovery excludes abstract classes and plant composites.

## Contracts and errors

Equipment declares class-level ports and Pydantic Params/Inputs/Outputs. Every numeric field
has a dimensional description and physical constraints. Use K, Pa, kg/s, m, W and s internally;
convert raw data at configuration boundaries. Correlation-specific legacy bases remain explicit.

Use `module(inputs, streams_in)` so observer hooks run. Direct `forward` still validates input
and result contracts but bypasses hooks. Return `ModuleResult(outputs, streams)`.
Parameter updates revalidate the complete owning schema. `state_dict` contains design data;
transient process state travels through `initial_state` and `step` separately.

Missing measured data skips only the affected twin and records a reason. Invalid physics,
misspelled configuration and unknown ports raise clear errors; do not silently discard them.
No sensor columns, file paths or database access belong in equipment calculations.

## Verification

```bash
poetry run black --check gemini tests examples
poetry run isort --check-only gemini tests examples
poetry run flake8 gemini tests examples
poetry run pytest tests
```

Use the existing Python 3.11 environment. Optional Parquet export requires the `parquet` extra.
