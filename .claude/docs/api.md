# Public API

Use `import gemini as gm`. Interactive completion exposes exactly `Engine`, `Clock`, `Dataset`,
`Profile`, `Stream`, `Fluid`, `BRINE`, `WATER`, `load_plant`, `modules`, `plants`, `optim`, and
`__version__`. New top-level exports require a concrete common user workflow and a documented
reason. Equipment classes, `Module`, `Sequential`, balance helpers and wiring observers are
available through `gm.modules`; handwritten plants through `gm.plants`.

Load a GEMINI project directory or saved JSON with `gm.load_plant(path)`. The returned plant
owns `bindings`, recursive `param_history`, `params_at(t)`, `apply_params_at(t)`, and
`column_units()`. `plant.save(path)` preserves the current design, all histories, explicit
parameter overrides, fluids, bindings and import diagnostics. `PlantConfig` is a serialization
schema, never a separate argument to an engine or optimizer call. Custom plant reconstruction
requires a discoverable plant class implementing `from_config`; checkpoints do not pickle code.

```python
import gemini as gm
plant = gm.load_plant("datasets/geothermal_doublet")
data = gm.Dataset.from_csv("datasets/geothermal_doublet/geothermal_example_dataset.csv")
engine = gm.Engine()
results = engine.replay(plant, data)
print(results["doublet.esp"].power)
print(results.summary())
engine.save_checkpoint("runs/replay.ckpt")
restored = gm.Engine.load_checkpoint("runs/replay.ckpt")
results = restored.resume()
fit = gm.optim.calibrate(plant, data, "heat_exchanger", fields=["ua"],
                         end="2024-06-13T23:45:00Z")
plant.save("runs/my_plant.json")
```

The complete acceptance script is [00_quickstart.py](../../examples/00_quickstart.py), also
included verbatim in the README and executed by `tests/test_quickstart.py`. The workspace's
actual folder is `geothermal_doublet`; its HX is `heat_exchanger`, and root profile columns are
`Qp` and `ESP_freq`. Minimal profiles inherit explicitly saved secondary-loop and injection
setpoint assumptions; supplying those bound columns overrides the assumptions.

`gm.optim.calibrate` accepts `fields`, `start`, `end`, an optional `engine`, and `apply=True`.
Successful application replaces current values and stores explicit overrides; it adds no dated
snapshot. Use `apply=False` to leave the original untouched. Fits use only public engine replay
predictions, bounded/scaled optimizer coordinates, and normalized measured-output residuals.
Fit and holdout windows must remain separate. The quickstart intentionally fits the whole file
as an API demonstration; the reconciliation test fits only the first seven days.

`Results[path].field` is a pandas Series. `to_frame()` returns MultiIndex columns. `summary()`
reports evaluated/operating hours, output peaks, per-port energy J/MWh and peak W, alarms,
errors and missing-data counts/reasons. `Results.save/load` preserve exact values using
Parquet when available or CSV plus JSON metadata. `save_csv/save_parquet` produce conventional
analysis files. `Results` and callback classes remain advanced APIs under `core.engine`;
ordinary load/run/save/resume/calibrate workflows need no `core.*` imports.
