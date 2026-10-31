"""Simulate a plant and read the results in the units you want.

Shows ``gm.simulate``, ``Results.get``, ``Results.summary``, ``units=``, ``Results.to_frame`` and
``Results.errors``.

Run with ``python examples/basics/05_simulate_and_results.py``.
"""

import os
from pathlib import Path

import pandas as pd

import gemini as gm

INPUTS = Path(__file__).resolve().parents[2] / "inputs"
MONTH = INPUTS / "doublet_heat/doublet_2024_15min_month.csv"
DATA = Path(os.environ.get("GEMINI_EXAMPLE_DATASET", MONTH))
UNITS = {"power": "MW", "temperature": "degC", "pressure": "bar"}


def main():
    """Simulate the data and read one series, one summary and one table of the run."""
    plant = gm.plants.example("DoubletHeatPlant")
    frame = pd.read_csv(DATA, parse_dates=["time"])
    results = gm.simulate(plant, plan=gm.Dataset.from_frame(frame, time_column="time"))
    print(f"Steps:            {len(results)}, failed rows: {len(results.errors())}")

    duty = results.get("heat_exchanger", "duty", units=UNITS)
    print(f"First duty:       {duty['value'][0]:.3f} {duty['unit']}")
    head = results.summary("injection_pump", units=UNITS)["injection_pump"]["head"]
    print(f"Lowest pump head: {head['min']['value']:.2f} {head['min']['unit']}")
    print(f"Highest pump head: {head['max']['value']:.2f} {head['max']['unit']}")

    table = results.to_frame(units=UNITS)
    print(f"Table:            {table.shape[0]} rows, {table.shape[1]} columns")
    print(f"Hot outlet mean:  {table['heat_exchanger.hot_out_T'].mean():.2f} °C")
    print(f"Unit of duty:     {table.attrs['units']['heat_exchanger.duty']}")


if __name__ == "__main__":
    main()
