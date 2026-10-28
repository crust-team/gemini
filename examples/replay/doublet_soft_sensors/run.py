"""Replay measured twins and summarize soft sensors.

Run: python examples/replay/doublet_soft_sensors/run.py.
"""

import pandas as pd

import gemini as gm
from examples.shared.doublet_heat.plant import DoubletHeatPlant

shared = "examples/shared/doublet_heat"
plant = DoubletHeatPlant.load(f"{shared}/plant.json")
frame = pd.read_csv(f"{shared}/doublet_2024_15min.csv", parse_dates=["time"])
data = gm.Dataset.from_frame(frame, time_column="time")
results = gm.Engine().replay(plant, data)
print(results["doublet.esp"].head.head())
print(results.summary())
