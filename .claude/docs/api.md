# Public API

Use `import gemini as gm`. The curated top level is `Engine`, `Clock`, `Dataset`, `Profile`,
`Stream`, `Ports`, `Fluid`, `BRINE`, `WATER`, `Quantity`, `no_outputs`, `units`, `runtime`,
`modules`, `plants`, `legacy`, `optim`, `errors` and `__version__`;
`tests/unit/test_public_api.py` pins this list. Loading, running, calibrating and converting
plants need no `core.*` imports. Writing a module imports its declarations (`Parameter`,
`Inlet`, `Control`, `Boundary`, `Output`, `Outlet`) and quantity aliases from
`gemini.core.types`; see [modules.md](modules.md). New top-level names require a concrete common
user workflow, documentation, and a public-API test.

`gm.modules` is `gemini.core.modules`. It exports `Module`, `ModuleList`, `ModuleDict`, every
shipped equipment class, the audits `collect_flows`, `energy_balance` and `mass_balance`, and
`trace_wiring`; composite plants such as `Doublet` are in `gm.plants`. The equipment classes are
(each one is described in [equipment.md](equipment.md)):

- pumps: `ESP`, `InjectionPump`, `CentrifugalPump`, `LineShaftPump`, `GasCompressor`;
- piping: `Pipe`, `Valve`, `Splitter`, `Mixer`, `PressurizationTank`;
- treatment: `Filter`, `Degasser`, `Blowdown`, `Desander`, `InhibitorDosing`, `Vent`;
- heat: `HeatExchanger`, `Boiler`, `HeatPump`, `AbsorptionUnit`, `AdsorptionChiller`, `CHP`,
  `Cooler`;
- subsurface: `ProductionReservoir`, `InjectionReservoir`, `ProductionWell`, `InjectionWell`,
  `ThermalDecline`, `AquiferStorage`, `BoreholeField`, `DownholeHeatExchanger`;
- storage and control: `ThermalStorage`, `IceStorage`, `PIDController`;
- power: `ORC`, `Separator`, `FlashTurbine`, `GridConnection`;
- demand: `HeatConsumer`, `CoolingConsumer`.

`BoosterPump` was removed; use `CentrifugalPump`, which has a real head and efficiency curve
instead of a pass-through with `modelled=False`. `Blowdown` now splits `feed_in` into
`retained_out` and `blowdown_out` under the `blowdown_fraction` control (it was a pass-through
`inlet` -> `outlet` with a `modelled` output).

Plants own their complete design. A plant class defined in `examples/` or user code uses
`plant.to_dict()`, `PlantClass.from_dict()`, `plant.save(path)`, and `PlantClass.load(path)`.
The file records the importable root class, each module's class path, current parameters, dated
histories, explicit overrides, fluids, bindings, and boundary defaults. Loading checks the format
version, the root class and the module paths; loading through the wrong class fails with both
stored and requested types in the message.

```python
import pandas as pd
import gemini as gm

plant = gm.Plant.load("examples/shared/doublet_heat/plant.json")
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
