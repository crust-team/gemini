# GEMINI geothermal suite

Composable geothermal equipment, plants built from data, in-memory data, and one finite engine for
simulation, historical replay, and externally scheduled live updates.

## Quickstart

The short form, with `profile` a DataFrame or `gm.Dataset` of the plant's inputs:

```python
import gemini as gm

plant = gm.plants.example("DoubletHeatPlant")
results = gm.simulate(plant, profile)
print(results.summary(units={"power": "MW", "temperature": "degC"}))
```

`gm.simulate`, `gm.replay`, `gm.live` and `gm.resume` cover a run in one call; `gm.Engine` is the
level for complex tasks, such as a run held in memory or a callback that reads the engine.

[examples/README.md](examples/README.md) lists every example in reading order, starting with
`python examples/quickstart.py`. The longer tour, from the repository root with Python 3.11, 3.12,
3.13 or 3.14:

```python
import pandas as pd

import gemini as gm

plant = gm.plants.example("DoubletHeatPlant")
design = {name: parameter.value for name, parameter in plant.doublet.esp.named_parameters()}
esp = gm.modules.ESP().update_params(**design)
stream = gm.Stream(flow="150 m3/h", T="80 C", p="20 bar")
out = esp(fluid_in=stream, frequency="50 Hz")
assert out.outputs.head == esp({"fluid_in": stream}, frequency="50 Hz").outputs.head
assert out.outputs.head == esp(stream, frequency="50 Hz").outputs.head
print(out.outputs.get("head", unit="bar"), out.outlets.fluid_out)
assert out.outlets.fluid_out is out.outlets["fluid_out"]

with gm.no_outputs():
    fluid_only = esp(fluid_in=out.outlets.fluid_out, frequency="50 Hz")
assert dict(fluid_only.outputs) == {}

esp.frequency = 50.0
plant.set_inputs({"doublet.esp.frequency": "50 Hz"})

frame = pd.read_csv("inputs/doublet_heat/doublet_2024_15min.csv", parse_dates=["time"])
data = gm.Dataset.from_frame(frame, time_column="time")

results = gm.replay(plant, data, checkpoint="runs/replay.ckpt")
print(results.to_frame(table="energy"))
print(results["doublet.esp"].power)
assert len(gm.resume("runs/replay.ckpt")) == len(results)

fit = gm.optim.calibrate(plant, data, params=[plant.get_parameter("heat_exchanger.thermal_conductance")])
print(fit)
```

A module is built without arguments and configured with `update_params`, which returns it. Calls
accept inlets by keyword, mapping or position; controls given at the call apply to that call only,
while assignment (`esp.frequency = 50.0`) or `plant.set_inputs` persists them by dotted path.

Plants are data. `gm.plants.names()` lists the shipped plants, `gm.plants.example(name)` returns
one with real values, `gm.plants.from_template("heating_cooling", {"absorption_chiller.enabled":
False})` fills a template with switchable units (`gm.plants.templates()` lists them), and
`gm.plants.convert_legacy(folder)` turns an old project folder into a plant spec. `gm.profiles`
holds the 2027 demand of the heating and cooling challenge, read from the organisers' files.

Data has two homes. `gm.plants.example` and `gm.profiles.get` read `inputs/`, which is in a source
checkout and not installed, and outside one they raise `inputs_missing`:

```text
gemini/assets/      # installed, read by gemini functions
  plants/           # plant structures, no parameter values
  templates/        # plant templates
inputs/             # repository only
  hackathon/        # the organisers' demand files and requirements, with a README
  plants/           # example values of plants
  doublet_heat/     # measured data
  legacy_project/   # an old project folder
```

A plant can be designed from its depth. A `Doublet` derives its reservoir, wells and pump from a few
design values, `gm.schedule` plans each day from the demand with no bindings to write, and
`gm.checks.limits` and `gm.economics` judge the run:

```python
plant.add("Doublet", name="d0", params={
    "depth": "2500 m", "gradient": "30 K/km", "surface_temperature": "12 degC",
    "permeability": "200 mD", "thickness": "100 m", "well_diameter": "0.244 m"})
plan = gm.schedule(plant, demand, rules)
results = gm.simulate(plant, plan)
```

`examples/cases/hackathon.py` is that path for the whole challenge plant.
Everything in the energy flow is a module and everything that crosses between modules goes through
a port. A plant starts at its edge modules: `ElectricityGrid`, `GasGrid`, `HeatingGrid`,
`CoolingGrid`, `WasteGrid`, `ChemicalGrid`, `Atmosphere` and `Formation`. Totals are read from them
(`gm.kpi.totals(plant, results)`) and `gm.checks.plant_balance(plant, results)` closes mass and
energy on them.

The application, not the package, reads CSV, databases, or APIs. `Dataset` accepts pandas, dicts,
records, NumPy, and profiles already in memory. A plant owns bindings and dated parameters, so
engine and optimizer calls never take a separate configuration.

See [api.md](.claude/docs/api.md), [modules.md](.claude/docs/modules.md),
[data.md](.claude/docs/data.md), [engine.md](.claude/docs/engine.md),
[legacy.md](.claude/docs/legacy.md) and [errors.md](.claude/docs/errors.md). Report bugs with the
output of `python -m gemini.utils.collect_env`.

## Testing

```bash
make test           # development profile: tests of what changed and what imports it
make test-release   # release profile: every tier on the full-year dataset
make lint           # flake8, black and isort
```

Always test what changed and everything that imports it; never run the full suite locally. See
[testing.md](.claude/docs/testing.md) for the profiles, markers, fixtures and golden-generation
rules.
