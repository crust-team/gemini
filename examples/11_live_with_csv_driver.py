"""Call a live run periodically, advancing only to newly available measurements."""

from pathlib import Path

import gemini as gm

DATA = Path(__file__).resolve().parents[1] / "datasets/geothermal_doublet"
plant = gm.load_plant(DATA)

from tempfile import TemporaryDirectory

data = gm.Dataset.from_csv_driver(DATA)
with TemporaryDirectory() as directory:
    checkpoint = Path(directory) / "live.ckpt"
    for now in ("2024-06-07T01:00:00Z", "2024-06-07T02:00:00Z", "2024-06-07T02:00:00Z"):
        new = gm.Engine().live(plant, data, checkpoint, now=now)
        print(now, "new rows:", len(new))
