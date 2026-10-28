"""Exercise the complete PyTorch-style module API."""

import pandas as pd

import gemini as gm
from examples.shared.doublet_heat.plant import DoubletHeatPlant

SHARED = "examples/shared/doublet_heat"

# a module, PyTorch style
plant = DoubletHeatPlant.load(f"{SHARED}/plant.json")
values = {name: p.value for name, p in plant.doublet.esp.named_parameters()}
esp = gm.modules.ESP(**values | {"setting_depth": "1200 m"})
s = gm.Stream(flow="150 m3/h", T="80 C", p="20 bar")
out = esp(suction=s, frequency="50 Hz")
print(out.outputs.head, out.outlets.discharge.p, out.outlets.electricity.P)
print(out.outputs.get("head", unit="bar"))
print(list(esp.inlets()), list(esp.controls()), list(esp.boundaries()))
print(list(esp.outputs()), list(esp.outlets()))
print(gm.modules.ESP.help())
print(gm.modules.list())

# uninitialized modules, keyword values, attribute assignment
empty = gm.modules.ESP()
assert not empty.is_initialized and "no_stages" in empty.missing_parameters()
empty.no_stages = 120
assert empty.no_stages == 120

# self-building plants and containers
assert isinstance(plant.filters, gm.modules.ModuleDict)
fresh = DoubletHeatPlant()
assert not fresh.is_initialized
fresh.load_state_dict(plant.state_dict())
assert fresh.is_initialized
print(plant)
print(sorted(plant.controls(recurse=True)))

# runtime settings
assert gm.runtime.get_precision() == "float64"
with gm.runtime.settings(precision="float32", display_units="field"):
    print(esp(suction=s, frequency=50))
assert gm.runtime.get_precision() == "float64"

# engine and calibration with parameter objects
df = pd.read_csv(f"{SHARED}/doublet_2024_15min.csv", parse_dates=["time"])
data = gm.Dataset.from_frame(df, time_column="time")
res = gm.Engine().replay(plant, data)
print(res["doublet.esp"].get("head", unit="bar").head())
fit = gm.optim.calibrate(plant, data, params=[plant.get_parameter("heat_exchanger.ua")])
print(fit)
