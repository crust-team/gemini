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
a = esp(suction=s, frequency="50 Hz")
esp.frequency = 50.0
b = esp(suction=s)
assert a.outputs.head == b.outputs.head

with gm.no_outputs():
    fluid_only = esp(suction=s)
assert dict(fluid_only.outputs) == {}
assert fluid_only.outlets.discharge == b.outlets.discharge


def clamp(module):
    """Clamp one call without changing the persistent command."""
    module.frequency = min(module.frequency, 45.0)


handle = esp.register_forward_pre_hook(clamp)
c = esp(suction=s)
handle.remove()
assert esp.frequency == 50.0
assert c.outputs.head < b.outputs.head
print(a.outputs.head, a.outlets.discharge.p, a.outputs.electricity)
print(a.outputs.get("head", unit="bar"))
print(list(esp.inlets()), list(esp.controls()), list(esp.boundaries()))
print(esp.get_control("frequency").unit)
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
plant.set_inputs({"doublet.esp.frequency": "50 Hz"})
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
