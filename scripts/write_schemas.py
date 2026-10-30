"""Write the generated schemas and every sample file of ``docs/schemas/``.

Run from the repository root after a change to a shape: ``python scripts/write_schemas.py``. The
schemas of the plant spec and the profile come from ``gm.plants.spec_schema()`` and
``gm.profiles.profile_schema()`` and those of the three return shapes from
``gemini.types.shapes``; the others are written by hand. The samples come from the example plant,
so other repositories can build against real documents.
"""

import json
from pathlib import Path

import pandas as pd

import gemini as gm
from gemini.types import shapes

ROOT = Path(__file__).parents[1]
SCHEMAS = ROOT / "docs" / "schemas"
DATA = ROOT / "examples" / "shared" / "doublet_heat" / "doublet_2024_15min_month.csv"
ROWS = 4
PROFILE_SOURCE = (
    "Format sample, not demand data: the replayed heat exchanger duty of the example plant."
)


def _results(plant):
    """Return a replay of the first rows of the example data."""
    frame = pd.read_csv(DATA, parse_dates=["time"]).iloc[:ROWS]
    return gm.replay(plant, gm.Dataset.from_frame(frame, time_column="time"))


def _profile_sample(results):
    """Return a document in the profile file format, marked as a sample."""
    series = results.get("heat_exchanger", "duty")
    return {
        "name": "format_sample",
        "description": "Shape of a demand profile file.",
        "source": PROFILE_SOURCE,
        "columns": {"heating_demand": {"unit": series["unit"], "quantity": "power"}},
        "time": series["time"],
        "values": {"heating_demand": series["value"]},
    }


def _problem_sample():
    """Return the problem of a real error."""
    try:
        gm.modules.get("Boilr")
    except gm.errors.GeminiError as error:
        return error.to_dict()
    raise gm.errors.ValidationError("gm.modules.get('Boilr') did not raise")


def documents():
    """Return ``{file name: document}`` of everything this script writes."""
    plant = gm.plants.example("DoubletHeatPlant")
    spec = plant.to_spec()
    results = _results(plant)
    return {
        "plant_spec.schema.json": gm.plants.spec_schema(),
        "profile.schema.json": gm.profiles.profile_schema(),
        **{f"{name}.schema.json": schema for name, schema in shapes.SCHEMAS.items()},
        "module_description.sample.json": gm.plants.example("Doublet").describe(),
        "plant_spec.sample.json": spec,
        "results_summary.sample.json": results.summary(),
        "profile.sample.json": _profile_sample(results),
        "value.sample.json": results.summary()["heat_exchanger"]["duty"]["mean"],
        "problem.sample.json": _problem_sample(),
        "check.sample.json": gm.checks.energy_balance(results),
    }


def main():
    """Write every document with sorted keys."""
    for name, document in documents().items():
        text = json.dumps(document, indent=2, sort_keys=True, allow_nan=False)
        (SCHEMAS / name).write_text(text + "\n")


if __name__ == "__main__":
    main()
