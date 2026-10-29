"""Inspect a saved plant: its tree, parameter count and root inputs.

Run from the repository root: PYTHONPATH=. python examples/core/basics/00_inspect_plant.py
"""

from examples.shared.doublet_heat.plant import DoubletHeatPlant

plant = DoubletHeatPlant.load("examples/shared/doublet_heat/plant.json")
print(plant)
print("Parameters:", len(list(plant.named_parameters())))
print("Root inputs:", list(plant.inputs(recurse=False)))
