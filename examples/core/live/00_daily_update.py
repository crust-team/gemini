"""Process two daily live updates once each, as an external scheduler would.

Run from the repository root: PYTHONPATH=. python examples/core/live/00_daily_update.py
"""

import os
from tempfile import TemporaryDirectory

import pandas as pd

import gemini as gm
from examples.shared.doublet_heat.plant import DoubletHeatPlant

shared = "examples/shared/doublet_heat"
plant = DoubletHeatPlant.load(f"{shared}/plant.json")
dataset_path = os.environ.get("GEMINI_EXAMPLE_DATASET", f"{shared}/doublet_2024_15min.csv")
frame = pd.read_csv(dataset_path, parse_dates=["time"])
start = frame["time"].iloc[0]
with TemporaryDirectory() as directory:
    checkpoint = f"{directory}/live.ckpt"
    for end in (start + pd.Timedelta(days=1), start + pd.Timedelta(days=2)):
        rows = frame[frame["time"] < end]
        data = gm.Dataset.from_frame(rows, time_column="time")
        print(end, len(gm.Engine().live(plant, data, checkpoint, now=end)))
