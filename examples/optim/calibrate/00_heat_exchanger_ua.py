"""Fit heat-exchanger conductance on seven days through the public calibration API."""

import pandas as pd

import gemini as gm
from examples.shared.doublet_heat.plant import DoubletHeatPlant

shared = "examples/shared/doublet_heat"
plant = DoubletHeatPlant.load(f"{shared}/plant.json")
frame = pd.read_csv(f"{shared}/doublet_2024_15min.csv", parse_dates=["time"])
data = gm.Dataset.from_frame(frame, time_column="time")
fit = gm.optim.calibrate(
    plant,
    data,
    params=[plant.get_parameter("heat_exchanger.ua")],
    end=frame.loc[7 * 96 - 1, "time"],
)
print(fit)
