"""Simulate the doublet heat plant on one month of data and print a few results.

Shows ``gm.Plant.load``, ``gm.Dataset.from_frame``, ``gm.simulate`` and ``Results.summary``.

Run with ``python examples/quickstart.py``.
"""

import os
from pathlib import Path

import pandas as pd

import gemini as gm

DATASETS = Path(__file__).resolve().parents[1] / "datasets"
MONTH = DATASETS / "doublet_heat/doublet_2024_15min_month.csv"
DATA = Path(os.environ.get("GEMINI_EXAMPLE_DATASET", MONTH))


def main():
    """Load the plant, simulate the data and print its heat, electricity and temperature."""
    plant = gm.Plant.load(DATASETS / "doublet_heat/plant.json")
    frame = pd.read_csv(DATA, parse_dates=["time"])
    results = gm.simulate(plant, gm.Dataset.from_frame(frame, time_column="time"))
    summary = results.summary(units={"power": "MW", "temperature": "degC"})
    print(f"Steps:              {len(results)}")
    print(f"Mean heat duty:     {summary['heat_exchanger']['duty']['mean']['value']:.2f} MW")
    print(f"Mean pump power:    {summary['injection_pump']['power_in']['mean']['value']:.3f} MW")
    print(f"Mean hot outlet:    {summary['heat_exchanger']['hot_out_T']['mean']['value']:.1f} °C")


if __name__ == "__main__":
    main()
