"""Fit HX conductance on seven days. Run: python examples/optim/calibrate/00_heat_exchanger_ua.py."""

import pandas as pd

import gemini as gm
from examples.shared.doublet_heat.plant import DoubletHeatPlant

shared = "examples/shared/doublet_heat"
plant = DoubletHeatPlant.load(f"{shared}/plant.json")
frame = pd.read_csv(f"{shared}/doublet_2024_15min.csv", parse_dates=["time"])
data = gm.Dataset.from_frame(frame, time_column="time")
fit = gm.optim.calibrate(
    plant, data, "heat_exchanger", fields=["ua"], end=frame.loc[7 * 96 - 1, "time"]
)
print(fit)
