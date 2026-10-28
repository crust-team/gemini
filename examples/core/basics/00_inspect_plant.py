"""Inspect a saved plant. Run: python examples/core/basics/00_inspect_plant.py."""

import gemini as gm
from examples.shared.doublet_heat.plant import DoubletHeatPlant

plant = DoubletHeatPlant.load("examples/shared/doublet_heat/plant.json")
print(plant)
print("Parameters:", len(list(plant.named_params())))
print("Root inputs:", list(plant.Inputs.model_fields))
print("Energy ports:", [name for name, kind in plant.outlets.items() if kind is not gm.Stream])
