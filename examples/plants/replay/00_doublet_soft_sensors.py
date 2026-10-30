"""Replay measured twins and summarize soft sensors.

Run from the repository root: PYTHONPATH=. python examples/plants/replay/00_doublet_soft_sensors.py
"""

import os

import pandas as pd

import gemini as gm

shared = "examples/shared/doublet_heat"
plant = gm.Plant.load(f"{shared}/plant.json")
dataset_path = os.environ.get("GEMINI_EXAMPLE_DATASET", f"{shared}/doublet_2024_15min.csv")
frame = pd.read_csv(dataset_path, parse_dates=["time"])
data = gm.Dataset.from_frame(frame, time_column="time")
results = gm.Engine(plant).replay(data)
print(results["doublet.esp"].head.head())
print(results.energy_report())
