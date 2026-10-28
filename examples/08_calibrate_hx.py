"""Fit HX conductance on the first week and inspect a held-out observation."""

from pathlib import Path

import gemini as gm

DATA = Path(__file__).resolve().parents[1] / "datasets/geothermal_doublet"
plant = gm.load_plant(DATA)

data = gm.Dataset.from_csv(DATA / "geothermal_example_dataset.csv")
fit = gm.optim.calibrate(plant, data, "heat_exchanger", ["ua"], end="2024-06-13T23:45:00Z")
print(fit)
result = gm.Engine().replay(
    plant, data, start="2024-06-14T00:00:00Z", end="2024-06-14T00:00:00Z", only=["heat_exchanger"]
)
print(result["heat_exchanger"].duty)
