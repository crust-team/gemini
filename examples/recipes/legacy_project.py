"""Convert an old GEMINI project folder into a plant.

Shows ``gm.plants.convert_legacy``, the one public entry to the old format, and
``gm.plants.from_dict``. The conversion gives the stored plant file of ``datasets/doublet_heat``.
The data file of the project is read here only to count its rows: its converted copy is the CSV
beside that plant file.

Run with ``python examples/recipes/legacy_project.py``.
"""

import json
from pathlib import Path

import pandas as pd

import gemini as gm

DATASETS = Path(__file__).resolve().parents[2] / "datasets"
PROJECT = DATASETS / "legacy_project"


def main():
    """Convert the folder and compare the result with the stored plant file."""
    spec = gm.plants.convert_legacy(PROJECT)
    plant = gm.plants.from_dict(spec)
    rows = pd.read_csv(PROJECT / "doublet_2024_old.csv", sep=";")
    stored = json.loads((DATASETS / "doublet_heat/plant.json").read_text())
    print(f"Old project rows:     {len(rows)}")
    print(f"Modules converted:    {len(plant.to_spec()['modules'])}")
    print(f"Same as the stored plant file: {spec == stored}")


if __name__ == "__main__":
    main()
