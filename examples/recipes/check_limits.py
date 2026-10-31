"""Judge a run against limits of your own.

Shows ``gm.checks.Limits``, its ``add``, and ``gm.checks.limits``. A violated limit is an answer,
not an error. The limits are assumptions of this recipe.

Run with ``python examples/recipes/check_limits.py``.
"""

import os
from pathlib import Path

import pandas as pd

import gemini as gm

INPUTS = Path(__file__).resolve().parents[2] / "inputs"
MONTH = INPUTS / "doublet_heat/doublet_2024_15min_month.csv"
DATA = Path(os.environ.get("GEMINI_EXAMPLE_DATASET", MONTH))


def limits():
    """Return one limit that holds and one that does not."""
    chosen = gm.checks.Limits()
    chosen.add("injection_pump.discharge_pressure", max="60 bar")
    chosen.add("heat_exchanger.duty", min="3.5 MW")
    return chosen


def main():
    """Simulate the data and print each limit with the worst value of the run."""
    plant = gm.plants.example("DoubletHeatPlant")
    frame = pd.read_csv(DATA, parse_dates=["time"])
    results = gm.simulate(plant, gm.Dataset.from_frame(frame, time_column="time"))
    print("Assumptions: at most 60 bar from the injection pump, at least 3.5 MW of heat")
    for check, unit in zip(gm.checks.limits(plant, results, limits()), ("bar", "MW")):
        verdict = "ok" if check["passed"] else "VIOLATED"
        worst = gm.units.convert(check["value"]["value"], check["value"]["unit"], unit)
        print(f"{check['name']:<34} {verdict:<9} worst {worst:.2f} {unit}")


if __name__ == "__main__":
    main()
