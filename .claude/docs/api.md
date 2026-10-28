# Public API

Use `import gemini as gm`. The curated top level includes `Engine`, `Clock`, `Dataset`, `Profile`,
`Stream`, `Fluid`, `Quantity`, `no_outputs`, `units`, `runtime`, `modules`, `legacy` and `optim`.
Common workflows need no `core.*` imports. New top-level names require a concrete common user
workflow, documentation, and a public-API test.

Plants own their complete design. A plant class defined in `examples/` or user code uses
`plant.to_dict()`, `PlantClass.from_dict()`, `plant.save(path)`, and `PlantClass.load(path)`.
The file records the importable root/child classes, current parameters, dated histories,
explicit overrides, fluids, bindings, and boundary defaults. Loading through the wrong class
fails with both stored and requested types in the message.

```python
import pandas as pd
import gemini as gm
from examples.shared.doublet_heat.plant import DoubletHeatPlant

plant = DoubletHeatPlant.load("examples/shared/doublet_heat/plant.json")
frame = pd.read_csv("examples/shared/doublet_heat/doublet_2024_15min.csv",
                    parse_dates=["time"])
data = gm.Dataset.from_frame(frame, time_column="time")
results = gm.Engine().replay(plant, data)
print(results["doublet.esp"].power)
print(results.summary())
```

`gm.optim.calibrate` fits only through public `Engine.replay`. With `apply=True`, a successful
fit replaces the current parameter as an explicit override; it does not add a dated snapshot.
Pass parameter objects, for example
`params=[plant.get_parameter("heat_exchanger.ua")]`; string paths and `ParamRef` are not part of
the API.
`Results[path].field` is a pandas Series and `Results.to_frame()` uses MultiIndex columns.
Direct module calls return `ModuleResult`, whose `outputs` and `outlets` support mapping and
attribute access. Use `get(name, unit="bar")` on direct or time-series results for display-unit
conversion.

Use `with gm.no_outputs():` (or `@gm.no_outputs()`) for fluid-only evaluation. These calls retain
validated outlets but skip computed outputs, output formulas and forward hooks.
