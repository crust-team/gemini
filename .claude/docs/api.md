# Public API

Use `import gemini as gm`. The curated top level is `Engine`, `Clock`, `Dataset`, `Profile`,
`Stream`, `Ports`, `Fluid`, `BRINE`, `WATER`, `Quantity`, `no_outputs`, `units`, `runtime`,
`modules`, `plants`, `legacy`, `optim`, `errors` and `__version__`;
`tests/unit/test_public_api.py` pins this list. Loading, running, calibrating and converting
plants need no `core.*` imports. Writing a module imports its declarations (`Parameter`,
`Inlet`, `Control`, `Boundary`, `Output`, `Outlet`) and quantity aliases from
`gemini.core.types`; see [modules.md](modules.md). New top-level names require a concrete common
user workflow, documentation, and a public-API test.

Plants own their complete design. A plant class defined in `examples/` or user code uses
`plant.to_dict()`, `PlantClass.from_dict()`, `plant.save(path)`, and `PlantClass.load(path)`.
The file records the importable root class, each module's class path, current parameters, dated
histories, explicit overrides, fluids, bindings, and boundary defaults. Loading checks the format
version, the root class and the module paths; loading through the wrong class fails with both
stored and requested types in the message.

```python
import pandas as pd
import gemini as gm
from examples.shared.doublet_heat.plant import DoubletHeatPlant

plant = DoubletHeatPlant.load("examples/shared/doublet_heat/plant.json")
frame = pd.read_csv("examples/shared/doublet_heat/doublet_2024_15min.csv", parse_dates=["time"])
data = gm.Dataset.from_frame(frame, time_column="time")
results = gm.Engine().replay(plant, data)
print(results["doublet.esp"].power)
print(results.summary())
```

`gm.optim.calibrate(plant, dataset, params, start=None, end=None, engine=None, apply=True)` fits
only through public `Engine.replay` and returns a `CalibrationResult`. With the default
`apply=True`, a successful fit replaces the current parameter as an explicit override; it does
not add a dated snapshot. `apply=False` leaves the plant unchanged. Pass parameter objects
declared `calibratable=True`, for example `params=[plant.get_parameter("heat_exchanger.ua")]`;
string paths and parameter reference types are not part of the API.

`Results[path].field` is a pandas Series and `Results.to_frame()` uses MultiIndex columns.
Direct module calls return `ModuleResult`, a frozen record that is not unpackable. Its `outlets`
is an immutable `Ports` mapping with mapping and attribute access; `outputs` provides the same
two access forms plus unit conversion. `result.outputs.get(name, unit="bar")` converts any output
from its declared unit. On time series, `results[path].get(field, unit="bar")` converts only the
six fields `head`, `pressure_drop`, `discharge_pressure`, `power`, `duty` and `thermal_power`,
because results store no per-field units.

Use `with gm.no_outputs():` (or `@gm.no_outputs()`) for fluid-only evaluation. These calls retain
validated outlets but skip computed outputs, output formulas and forward hooks.

## Errors

Every exception class is available as `gm.errors.<Name>` and derives from `gm.errors.GeminiError`
and the matching built-in exception. The classes and when each is raised are listed in
[errors.md](errors.md).
