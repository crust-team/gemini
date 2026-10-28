# Implementation conventions

Use Python 3.11, Black, isort, 100-character lines and Flake8 docstrings. Preserve captured
numbers. Intentional physical or numerical decisions require `NOTE(refactor)`, explanation and
regression evidence. Use SI internally: K, Pa, kg/s, m, W, J and s.

Dependencies flow:

`core.physics` ← `core.types` ← `core.modules` ← `core.data` ← `core.engine`
← `core.legacy` ← `optim` / `design` ← `agentic` ← `gemini/__init__`.

Core packages outside `core.legacy` never interpret old project names, tags, tables or node
mappings. Old-format knowledge stays in `gemini.core.legacy`, publicly available as `gm.legacy`.
Equipment performs no file or database access. Calibration predicts only through public replay.
Plants are handwritten; configuration files fill a tree but do not construct runtime wiring.

## Module rules

1. Assign declarations and children only in `__init__`.
2. Section order is `Modules`, `Parameters`, `Inlets`, `Controls`, `Boundaries`, `States`,
   `Outputs`, `Outlets`, using plain `# Section` comments without decorative dashes.
3. Controls are settable commands; boundaries are uncontrollable external conditions.
4. `forward` is exactly `forward(self, inlets)` and reads declared streams through the immutable
   `Ports` mapping, such as `inlets.suction`. Controls and boundaries are applied before the call
   and read as plain attributes such as `self.frequency`.
5. `forward` sections are `# Modules` and `# Outlets`, in that order with empty sections omitted.
   Only composites use `# Modules`; `forward` never assigns an attribute on `self`.
6. Leaves assign every plain output in `_compute_outputs(self, inlets, outlets)`. Composites use
   only `Output.of`, `Output.total` and `Output.ratio` declarations and never override it.
7. End every `forward` with `outlets = dict(...)` in declaration order, then `return outlets`.
   Zero- and one-outlet modules use the same dictionary shape.
8. Do not construct `ModuleResult` in module code; `Module.__call__` creates it.
9. Keep value arguments out of `__init__`; structural tree-shape arguments are the exception.
10. Never declare metadata or lists that `Module` derives.
11. Inlets and outlets carry `Stream` types only. Electricity, fuel and heat loss are outputs.
12. Pre-hooks are exactly `(module, inlets)` and forward hooks are exactly
    `(module, inlets, outlets)`.

Use dotted module paths consistently. Binding groups are `controls`, `boundaries`, `inlets`,
`measured` and `state`. Reject unknown ports and parameters. Missing observations skip only
their measured twin. Never disguise a thermal-only audit as full first-law closure or tune
against a holdout merely to meet a threshold.

Examples live under `examples/<area>/<category>/NN_<name>.py`; shared artifacts live in
`examples/shared/`, and generated output goes under ignored `runs/`.
