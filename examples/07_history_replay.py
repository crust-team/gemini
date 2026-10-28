"""Replay one week and inspect soft sensors and assessed health."""

from pathlib import Path

import gemini as gm

DATA = Path(__file__).resolve().parents[1] / "datasets/geothermal_doublet"
plant = gm.load_plant(DATA)

data = gm.Dataset.from_csv(DATA / "geothermal_example_dataset.csv")
results = gm.Engine().replay(plant, data, end="2024-06-13T23:45:00Z")
print(results["doublet.esp"].head.head())
print(results.summary())
