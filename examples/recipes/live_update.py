"""Process two daily live updates once each, as an external scheduler would.

Shows ``gm.live`` with a checkpoint that carries the run between calls.

Run with ``python examples/recipes/live_update.py``.
"""

import os
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

import gemini as gm

DATASETS = Path(__file__).resolve().parents[2] / "datasets"
MONTH = DATASETS / "doublet_heat/doublet_2024_15min_month.csv"
DATA = Path(os.environ.get("GEMINI_EXAMPLE_DATASET", MONTH))


def main():
    """Hand the rows of each day to ``gm.live`` and print how many were new."""
    plant = gm.Plant.load(DATASETS / "doublet_heat/plant.json")
    frame = pd.read_csv(DATA, parse_dates=["time"])
    start = frame["time"].iloc[0]
    with TemporaryDirectory() as folder:
        checkpoint = Path(folder) / "live.ckpt"
        for end in (start + pd.Timedelta(days=1), start + pd.Timedelta(days=2)):
            rows = gm.Dataset.from_frame(frame[frame["time"] < end], time_column="time")
            new = len(gm.live(plant, rows, checkpoint, now=end))
            print(f"Update of {end:%Y-%m-%d %H:%M} UTC: {new} new rows")


if __name__ == "__main__":
    main()
