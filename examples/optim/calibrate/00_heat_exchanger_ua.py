"""Fit heat-exchanger conductance on seven days through the public calibration API.

Run from the repository root: PYTHONPATH=. python examples/optim/calibrate/00_heat_exchanger_ua.py
"""

import os

import pandas as pd

import gemini as gm

shared = "examples/shared/doublet_heat"
plant = gm.Plant.load(f"{shared}/plant.json")
dataset_path = os.environ.get("GEMINI_EXAMPLE_DATASET", f"{shared}/doublet_2024_15min.csv")
frame = pd.read_csv(dataset_path, parse_dates=["time"])
data = gm.Dataset.from_frame(frame, time_column="time")
fit = gm.optim.calibrate(
    plant,
    data,
    params=[plant.get_parameter("heat_exchanger.ua")],
    end=frame.loc[7 * 96 - 1, "time"],
)
print(fit)
