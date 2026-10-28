# Implementation conventions

Use Python 3.11, Black/isort, 100-character lines, and flake8 docstrings. Preserve captured
numbers. Intentional physical or numerical decisions require `NOTE(refactor)`, explanation, and
regression evidence. Use SI internally: K, Pa, kg/s, m, W, J, s.

Dependencies flow:

`core.physics` ← `core.types` ← `core.modules` ← `core.data` ← `core.engine`
← `legacy` ← `optim` / `design` ← `agentic` ← `gemini/__init__`.

Core packages never interpret old project names, tags, tables, or node mappings. All old-format
knowledge is in `gemini.legacy`. Equipment performs no file/database access. Data sampling does
not import clocks. Calibration predicts only through public replay. Plants are handwritten;
configuration files do not construct runtime wiring.

Examples live under `examples/<category>/<name>/run.py`; shared plant/data artifacts live in
`examples/shared/`. No example-specific plant or data belongs inside `gemini/`. Example output
goes under ignored `runs/`.

Use dotted module paths consistently. Reject unknown ports/parameters. Missing observations skip
only their measured twin. Never disguise a thermal-only audit as full first-law closure or tune
against a holdout merely to meet a threshold.
