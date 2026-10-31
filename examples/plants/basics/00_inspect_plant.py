"""Inspect a saved plant: its tree, parameter count and root inputs.

Run from the repository root: PYTHONPATH=. python examples/plants/basics/00_inspect_plant.py
"""

import gemini as gm

plant = gm.Plant.load("datasets/doublet_heat/plant.json")
print(plant)
print("Parameters:", len(list(plant.named_parameters())))
print("Root inputs:", list(plant.inputs(recurse=False)))
