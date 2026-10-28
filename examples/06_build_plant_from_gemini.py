"""Load, inspect and round-trip a portable plant."""

from pathlib import Path

import gemini as gm

DATA = Path(__file__).resolve().parents[1] / "datasets/geothermal_doublet"
plant = gm.load_plant(DATA)

from tempfile import TemporaryDirectory

print(plant)
with TemporaryDirectory() as directory:
    path = Path(directory) / "plant.json"
    plant.save(path)
    assert gm.load_plant(path).state_dict() == plant.state_dict()
print(f"Round-trip complete; {len(plant.config.ignored)} documented import diagnostics.")
