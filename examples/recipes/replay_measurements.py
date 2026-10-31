"""Replay measured data through the equipment twins and read the soft sensors.

Shows ``gm.replay``, ``results[path].get`` and the energy table of ``Results.to_frame``.

Run with ``python examples/recipes/replay_measurements.py``.
"""

import os
from pathlib import Path

import pandas as pd

import gemini as gm

INPUTS = Path(__file__).resolve().parents[2] / "inputs"
MONTH = INPUTS / "doublet_heat/doublet_2024_15min_month.csv"
DATA = Path(os.environ.get("GEMINI_EXAMPLE_DATASET", MONTH))


def main():
    """Replay the data, then print the pump head and the energy of each module."""
    plant = gm.plants.example("DoubletHeatPlant")
    frame = pd.read_csv(DATA, parse_dates=["time"])
    results = gm.replay(plant, gm.Dataset.from_frame(frame, time_column="time"))
    head = results["doublet.esp"].get("head", unit="bar")
    print(f"ESP head, first step:  {head.iloc[0]:.4f} bar")
    print(f"ESP head, mean:        {head.mean():.4f} bar")
    print("module, port: energy, peak, operating hours, alarms")
    table = results.to_frame(table="energy")
    for (module, port), row in table[(table["peak_W"] > 0) | (table["alarms"] > 0)].iterrows():
        print(
            f"{module + ' ' + port:<26} {row['energy_MWh']:8.2f} MWh {row['peak_W'] / 1e3:9.1f} kW "
            f"{row['operating_hours']:6.0f} h {row['alarms']:6.0f} alarms"
        )


if __name__ == "__main__":
    main()
