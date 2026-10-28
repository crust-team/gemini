# Implementation conventions

Use the smallest clear implementation, Python 3.11, Black/isort, 100-character lines and flake8
with docstrings. Preserve golden numbers. Intentional numerical decisions require
`NOTE(refactor)`, physical explanation and regression evidence.

Dependencies flow:

`core.physics` ← `core.types` ← `core.modules` ← `core.config` / `core.modes` / `core.engine`
← `design` / `optim` ← `agentic`.

Physics owns correlations and conversions. Types owns quantities, Fluid, flows, Profile, results
and Cost; it never imports modules. Equipment contains no configuration/data access. Plant
`from_config` factories may import the registry locally solely for child construction. Physical
geometry models retain direct quantity metadata without importing types upward.

Every numeric module contract field uses a quantity alias or the documented, tested allow-list.
Use SI internally: K, Pa, kg/s, m, W, J, s. Explicit exceptions are legacy polynomial bases and
mm/year corrosion diagnostics. Raw data conversion occurs at input boundaries. All ports have
explicit Flow types; built-in energy ports report consumption/release as outputs.

Plants are handwritten classes: child construction in `__init__`, wiring in `forward`.
Configurations select plant type and dated design data; diagrams verify wiring, never build it.
Use dotted child paths consistently across snapshots, calibration, bindings and results.
No compatibility shims for removed modules or string fluid registries.

Use `module(...)` for hooks and retained result trees. Reject unknown ports and parameters.
Missing observations skip only their measured twin, recording a reason. Invalid physics raises.
Absent diagnostic models are explicitly unassessed. Never disguise a thermal-only balance as
full first-law closure or tune against the holdout period to meet an accuracy threshold.

```bash
poetry run black --check gemini tests examples
poetry run isort --check-only gemini tests examples
poetry run flake8 gemini tests examples
poetry run pytest tests
```

Use the existing Python 3.11 environment; optional Parquet export requires the parquet extra.
