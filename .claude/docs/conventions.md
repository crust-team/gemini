# Implementation conventions

Use Python 3.11, Black, isort, 100-character lines and Flake8 docstrings. Preserve captured
numbers. Intentional physical or numerical decisions require `NOTE(refactor)`, explanation and
regression evidence. Use SI internally: K, Pa, kg/s, m, W, J and s.

Dependencies flow:

`core.physics` ← `core.types` ← `core.modules` ← `core.data` ← `core.engine`
← `legacy` ← `optim` / `design` ← `agentic` ← `gemini/__init__`.

Core packages never interpret old project names, tags, tables or node mappings. Old-format
knowledge stays in `gemini.legacy`. Equipment performs no file or database access. Calibration
predicts only through public replay. Plants are handwritten; configuration files fill a tree but
do not construct runtime wiring.

## Module rules

1. Assign declarations and children only in `__init__`.
2. Section order is `Modules`, `Parameters`, `Inlets`, `Controls`, `Boundaries`, `Outputs`,
   `Outlets`, using plain `# Section` comments without decorative dashes.
3. Controls are settable commands; boundaries are uncontrollable external conditions.
4. `forward` has exactly the declared inlet/control/boundary names as plain arguments.
5. Assign outputs and return outlets. Do not construct `ModuleResult` in equipment code.
6. Keep value arguments out of `__init__`; structural tree-shape arguments are the exception.
7. Never declare metadata or lists that `Module` derives.

Use dotted module paths consistently. Binding groups are `controls`, `boundaries`, `inlets`,
`measured` and `state`. Reject unknown ports and parameters. Missing observations skip only
their measured twin. Never disguise a thermal-only audit as full first-law closure or tune
against a holdout merely to meet a threshold.

Examples live under `examples/<area>/<category>/NN_<name>.py`; shared artifacts live in
`examples/shared/`, and generated output goes under ignored `runs/`.
