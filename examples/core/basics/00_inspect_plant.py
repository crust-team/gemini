"""Inspect a saved plant. Run: python examples/core/basics/00_inspect_plant.py."""

import gemini as gm
from examples.shared.doublet_heat.plant import DoubletHeatPlant

plant = DoubletHeatPlant.load("examples/shared/doublet_heat/plant.json")
print(plant)
print("Parameters:", len(list(plant.named_parameters())))
print("Root inputs:", list(plant.inputs(recurse=False)))
print(
    "Energy ports:",
    [name for name, declaration in plant.outlets().items() if declaration.kind is not gm.Stream],
)
