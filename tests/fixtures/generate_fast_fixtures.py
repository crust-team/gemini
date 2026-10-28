"""Generate the July 2024 fast dataset and its unchanged-code replay golden."""

from pathlib import Path

import pandas as pd

import gemini as gm
from examples.shared.doublet_heat.plant import DoubletHeatPlant

ROOT = Path(__file__).parents[2]
SHARED = ROOT / "examples/shared/doublet_heat"
SOURCE = SHARED / "doublet_2024_15min.csv"
FAST = SHARED / "doublet_2024_15min_month.csv"
GOLDEN = ROOT / "tests/fixtures/module_api_fast/replay.csv.gz"


def generate_dataset():
    """Copy July rows byte-for-byte from the immutable full dataset."""
    lines = SOURCE.read_text().splitlines(keepends=True)
    selected = [lines[0], *(line for line in lines[1:] if line.startswith("2024-07-"))]
    FAST.write_text("".join(selected))


def generate_golden():
    """Replay the generated month and save its exact result frame."""
    frame = pd.read_csv(FAST, parse_dates=["time"])
    data = gm.Dataset.from_frame(frame, time_column="time")
    plant = DoubletHeatPlant.load(SHARED / "plant.json")
    GOLDEN.parent.mkdir(parents=True, exist_ok=True)
    gm.Engine().replay(plant, data).to_frame().to_csv(
        GOLDEN, compression={"method": "gzip", "mtime": 0}
    )


if __name__ == "__main__":
    generate_dataset()
    generate_golden()
