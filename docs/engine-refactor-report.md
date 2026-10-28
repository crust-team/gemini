# Engine, in-memory data, and legacy-boundary refactor

The runtime now has one finite `Engine` for simulate, replay, and live calls. Plants own their
bindings, dated parameters, fluids, serialization, and module tree. Core data is one in-memory
pandas-backed `Dataset`; all file/database acquisition is caller code. Old project conversion is
isolated under `gemini.legacy`.

## Main moves and removals

- Removed `gemini/core/config/`; binding/date/column types live in `core/types/bindings.py`, and
  plant JSON lives on `Module.to_dict/from_dict/save/load`.
- Removed `gemini/core/data/drivers/` and the Influx/AVEVA dependencies.
- Moved the example plant to `examples/shared/doublet_heat/plant.py` as `DoubletHeatPlant`.
- Moved old project files to `examples/legacy/gemini_project_bridge/old_project/` and generated
  the committed SI `plant.json` and `doublet_2024_15min.csv` in the shared example.
- Organized numbered scripts as package/category/NN_name.py examples.
- Reorganized tests into unit, integration, e2e, and fixtures.

## Checkpoints

Version 1 manifests contain the importable plant class, complete plant dictionary, module states,
clock, last committed timestamp, dataset fingerprint, result generation, and unfinished data
generation. Results and remaining rows are published before the manifest's atomic replacement.
CSV fallback JSON-encodes cells, preserving exact float bits. Live stores no input rows and uses
the committed position as an idempotent watermark.

## Verification

- Full 17,280-row replay: 16.89 seconds, zero recorded errors.
- Full suite: 148 passed in 268.71 seconds.
- Full reconciliation: 4 passed in 55.67 seconds; captured physical metrics remain within their
  documented thresholds.
- Literal quickstart passed, including full-data calibration, save/load, checkpoint resume,
  simulation, and two live calls.
- Legacy round trip and all six example subprocesses passed.

The SI CSV is parsed by ordinary pandas as requested. Its decimal parser can differ from the
pre-conversion raw-unit path by roughly 1e-15 in chained scenario values; the golden assertion
uses a 1e-14 relative tolerance for this representation-only effect. Replay golden frames remain
exact, and checkpoint interruption/resume remains bit-exact.
