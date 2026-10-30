"""Tour the module API: calls, hooks, skipped outputs, plants, runtime settings and the engine.

Run from the repository root: PYTHONPATH=. python examples/plants/basics/01_module_api.py
"""

import os

import pandas as pd

import gemini as gm

SHARED = "examples/shared/doublet_heat"


def configured_esp(plant):
    """Build a standalone ESP from the plant's pump design, set 1200 m deeper."""
    values = {name: p.value for name, p in plant.doublet.esp.named_parameters()}
    return gm.modules.ESP().update_params(**values | {"setting_depth": "1200 m"})


def call_forms(esp, stream):
    """Keyword, mapping and positional inlets agree; a persisted control applies by default."""
    a = esp(suction=stream, frequency="50 Hz")
    b = esp({"suction": stream}, frequency="50 Hz")
    c = esp(stream, frequency="50 Hz")
    assert a.outputs.head == b.outputs.head == c.outputs.head
    esp.frequency = 50.0
    persistent = esp(suction=stream)
    assert a.outputs.head == persistent.outputs.head
    print(a.outputs.head, a.outlets.discharge.p, a.outputs.electricity)
    print(a.outputs.get("head", unit="bar"))
    return persistent


def fluid_only(esp, stream, persistent):
    """``no_outputs`` keeps the outlets and skips every computed output."""
    with gm.no_outputs():
        result = esp(suction=stream)
    assert dict(result.outputs) == {}
    assert result.outlets.discharge == persistent.outlets.discharge


def clamp(module, inlets):
    """Clamp one call without changing the persistent command."""
    module.frequency = min(module.frequency, 45.0)


def clamped_call(esp, stream, persistent):
    """Clamp the frequency of one call with a pre-hook."""
    handle = esp.register_forward_pre_hook(clamp)
    clamped = esp(suction=stream)
    handle.remove()
    assert esp.frequency == 50.0
    assert clamped.outputs.head < persistent.outputs.head


def describe(esp):
    """List declarations, units and the class help."""
    print(list(esp.inlets()), list(esp.controls()), list(esp.boundaries()))
    print(esp.get_control("frequency").unit)
    print(list(esp.outputs()), list(esp.outlets()))
    print(gm.modules.ESP.help())
    print(gm.modules.__all__)


def uninitialized():
    """Show that a new module reports missing parameters until they are assigned."""
    empty = gm.modules.ESP()
    assert not empty.is_initialized and "no_stages" in empty.missing_parameters()
    empty.no_stages = 120
    assert empty.no_stages == 120


def plants_and_containers(plant):
    """Plants build their own tree; state dictionaries copy a design into a fresh plant."""
    assert isinstance(plant.filters, gm.modules.ModuleDict)
    fresh = gm.plants.get("DoubletHeatPlant")
    assert not fresh.is_initialized
    fresh.load_state_dict(plant.state_dict())
    assert fresh.is_initialized
    print(plant)
    plant.set_inputs({"doublet.esp.frequency": "50 Hz"})
    print(sorted(plant.controls()))


def runtime_settings(esp, stream):
    """Apply runtime settings inside a ``with`` block; they are restored afterwards."""
    assert gm.runtime.get_precision() == "float64"
    with gm.runtime.settings(precision="float32", display_units="field"):
        print(esp(suction=stream, frequency=50))
    assert gm.runtime.get_precision() == "float64"


def engine_and_calibration(plant):
    """Replay the shared data and calibrate the heat exchanger UA with a parameter object."""
    dataset_path = os.environ.get("GEMINI_EXAMPLE_DATASET", f"{SHARED}/doublet_2024_15min.csv")
    frame = pd.read_csv(dataset_path, parse_dates=["time"])
    data = gm.Dataset.from_frame(frame, time_column="time")
    results = gm.Engine(plant).replay(data)
    print(results["doublet.esp"].get("head", unit="bar").head())
    fit = gm.optim.calibrate(plant, data, params=[plant.get_parameter("heat_exchanger.ua")])
    print(fit)


def main():
    """Run every part of the tour in order."""
    plant = gm.Plant.load(f"{SHARED}/plant.json")
    esp = configured_esp(plant)
    stream = gm.Stream(flow="150 m3/h", T="80 C", p="20 bar")
    persistent = call_forms(esp, stream)
    fluid_only(esp, stream, persistent)
    clamped_call(esp, stream, persistent)
    describe(esp)
    uninitialized()
    plants_and_containers(plant)
    runtime_settings(esp, stream)
    engine_and_calibration(plant)


if __name__ == "__main__":
    main()
