"""Process two daily live updates once. Run: python examples/live/daily_update/run.py."""

from tempfile import TemporaryDirectory

import pandas as pd

import gemini as gm
from examples.shared.doublet_heat.plant import DoubletHeatPlant

shared = "examples/shared/doublet_heat"
plant = DoubletHeatPlant.load(f"{shared}/plant.json")
frame = pd.read_csv(f"{shared}/doublet_2024_15min.csv", parse_dates=["time"])
with TemporaryDirectory() as directory:
    checkpoint = f"{directory}/live.ckpt"
    for end in ("2024-06-08T00:00:00Z", "2024-06-09T00:00:00Z"):
        rows = frame[frame["time"] < end]
        data = gm.Dataset.from_frame(rows, time_column="time")
        print(end, len(gm.Engine().live(plant, data, checkpoint, now=end)))
