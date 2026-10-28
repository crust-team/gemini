# GEMINI geothermal suite

Composable equipment and handwritten geothermal plants with a small Python API. Load a plant,
choose a dataset, then simulate assumed inputs, replay history or process a finite live window.
Plants carry their sensor bindings, dated parameters and fluids; checkpoints restore the entire
run. The engine never schedules itself or sleeps.

## Setup

Use Python 3.11 and install this package in your environment (`pip install -e .`). The optional
`parquet` extra enables Parquet result files; CSV plus JSON metadata works without it. From the
repository root, run `python examples/00_quickstart.py`.

## Quickstart

The checked-in project folder is named `geothermal_doublet`. Its actual HX path is
`heat_exchanger`; profiles use the source column names `Qp` and `ESP_freq`.

```python
import gemini as gm

# Load a GEMINI project folder or our own plant.json.
plant = gm.load_plant("datasets/geothermal_doublet")
print(plant)

data = gm.Dataset.from_csv("datasets/geothermal_doublet/geothermal_example_dataset.csv")
engine = gm.Engine()
res = engine.replay(plant, data)
print(res.summary())
esp_power = res["doublet.esp"].power

engine.save_checkpoint("runs/replay.ckpt")
engine2 = gm.Engine.load_checkpoint("runs/replay.ckpt")
res2 = engine2.resume()

fit = gm.optim.calibrate(plant, data, "heat_exchanger", fields=["ua"])
print(fit)
plant.save("runs/my_plant.json")
assert gm.load_plant("runs/my_plant.json").state_dict() == plant.state_dict()

profiles = {
    "Qp": gm.Profile.constant(150, unit="m3/h", clock=gm.Clock.days(2027, 1, 1, days=1)),
    "ESP_freq": gm.Profile.constant(55, unit="Hz", clock=gm.Clock.days(2027, 1, 1, days=1)),
}
sim = engine.simulate(
    plant, gm.Dataset.from_profiles(profiles), clock=gm.Clock.days(2027, 1, 1, days=1)
)
print(sim.summary())

live_data = gm.Dataset.from_csv_driver("datasets/geothermal_doublet")
out = engine.live(plant, live_data, checkpoint="runs/live.ckpt", now="2024-06-08T00:00:00Z")
```

The quickstart's two assumed controls inherit the plant's explicit secondary-loop defaults:
40 kg/s at 20 °C and 5 bar, and a 51.5-bar injection setpoint. Supply the corresponding root-bound
columns to replace those assumptions. The whole-file calibration demonstrates the API; validation
fits only the first week and evaluates the remaining observations separately.

## Execution and persistence

`replay` predicts each equipment module on measured boundaries. `simulate` runs the handwritten
plant's real wiring. `live` processes only new available ticks up to `now`, saves its checkpoint,
and returns this call's new rows. An external scheduler calls it again. `engine.results` retains
cumulative results; timestamp-keyed sinks should be idempotent.

A checkpoint stores plant design, states, finite clock, completed position, dataset descriptor
and a sibling result generation. File/remote inputs must remain stable for exact resume. CSV
and in-memory inputs work offline. Influx/AVEVA adapters reference credentials by environment
variable names; real service access requires local configuration.

The supplied project's known physical limitations remain visible: zero ESP power coefficients,
a mismatched ESP head curve, and a changing apparent HX conductance. Passing regression tests
does not establish the original pump-accuracy or alarm-rate targets. See the numerical notes
and engine report for measured values.

## Documentation and development

- [Public API](.claude/docs/api.md)
- [Engine, clocks, callbacks and checkpoints](.claude/docs/engine.md)
- [Datasets, units and alignment](.claude/docs/data.md)
- [Module authoring](.claude/docs/modules.md)
- [Numerical decisions and known limitations](.claude/docs/refactor-notes.md)
- [Engine refactor report](docs/engine-refactor-report.md)

Run `black --check gemini tests examples`, `isort --check-only gemini tests examples`,
`flake8 gemini tests examples`, and `pytest tests`. Golden fixtures must not change. The full
17,280-row reconciliation and every example run in the default suite; external AVEVA integration
is skipped when credentials are absent.
