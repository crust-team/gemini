# GEMINI geothermal suite

Composable geothermal equipment, handwritten plants, in-memory data, and one finite engine for
simulation, historical replay, and externally scheduled live updates.

## Quickstart

Run from the repository root with Python 3.11:

```python
import pandas as pd

import gemini as gm
from examples.shared.doublet_heat.plant import DoubletHeatPlant

SHARED = "examples/shared/doublet_heat"
plant = DoubletHeatPlant.load(f"{SHARED}/plant.json")
esp = gm.modules.ESP(
    **{name: parameter.value for name, parameter in plant.doublet.esp.named_parameters()}
)
stream = gm.Stream(flow="150 m3/h", T="80 C", p="20 bar")
out = esp(suction=stream, frequency="50 Hz")
assert out.outputs.head == esp({"suction": stream}, frequency="50 Hz").outputs.head
assert out.outputs.head == esp(stream, frequency="50 Hz").outputs.head
print(out.outputs.get("head", unit="bar"), out.outlets.discharge)
assert out.outlets.discharge is out.outlets["discharge"]

with gm.no_outputs():
    fluid_only = esp(suction=out.outlets.discharge, frequency="50 Hz")
assert dict(fluid_only.outputs) == {}

# Persist controls by assignment, or set any leaf input by path.
esp.frequency = 50.0
plant.set_inputs({"doublet.esp.frequency": "50 Hz"})

df = pd.read_csv(f"{SHARED}/doublet_2024_15min.csv", parse_dates=["time"])
data = gm.Dataset.from_frame(df, time_column="time")

engine = gm.Engine()
results = engine.replay(plant, data)
print(results.summary())
print(results["doublet.esp"].power)

engine.save_checkpoint("runs/replay.ckpt")
restored = gm.Engine.load_checkpoint("runs/replay.ckpt")
assert len(restored.resume()) == len(results)

fit = gm.optim.calibrate(
    plant, data, params=[plant.get_parameter("heat_exchanger.ua")]
)
print(fit)
```

The application—not the package—reads CSV, databases, or APIs. `Dataset` accepts pandas, dicts,
records, NumPy, and profiles already in memory. A plant owns bindings and dated parameters, so
engine and optimizer calls never take a separate configuration.

See [.claude/docs/api.md](.claude/docs/api.md),
[data.md](.claude/docs/data.md), [engine.md](.claude/docs/engine.md), and
[legacy.md](.claude/docs/legacy.md). Testing commands are:

```bash
python -m pytest
python -m pytest -n auto -m "e2e or slow" --dataset=fast
python -m pytest -n auto -m "" --dataset=slow
```

The first command is the under-30-second unit/integration tier. The second runs real workflows
on the committed July month; the final command is the full-year merge gate. See
[testing.md](.claude/docs/testing.md) for markers, fixtures and golden-generation rules.
