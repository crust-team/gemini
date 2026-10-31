"""Fit the heat-exchanger conductance on seven days of data.

Shows ``gm.optim.calibrate`` and ``CalibrationResult``. A calibration takes the parameter object
of a calibratable parameter, which ``get_parameter`` gives.

Run with ``python examples/recipes/calibrate.py``.
"""

import os
from pathlib import Path

import pandas as pd

import gemini as gm

INPUTS = Path(__file__).resolve().parents[2] / "inputs"
MONTH = INPUTS / "doublet_heat/doublet_2024_15min_month.csv"
DATA = Path(os.environ.get("GEMINI_EXAMPLE_DATASET", MONTH))
STEPS_PER_DAY = 96
CONDUCTANCE = "heat_exchanger.thermal_conductance"


def main():
    """Fit on the first week and print the conductance and the residual before and after."""
    plant = gm.plants.example("DoubletHeatPlant")
    frame = pd.read_csv(DATA, parse_dates=["time"])
    data = gm.Dataset.from_frame(frame, time_column="time")
    end = frame.loc[7 * STEPS_PER_DAY - 1, "time"]
    fit = gm.optim.calibrate(plant, data, params=[plant.get_parameter(CONDUCTANCE)], end=end)
    before, after = [next(iter(values.values())) / 1e3 for values in (fit.initial, fit.fitted)]
    print(f"Conductance:    {before:.1f} -> {after:.3f} kW/K")
    print(f"Normalised RMS: {fit.rms_before:.6g} -> {fit.rms_after:.6g}")
    print(f"Evaluations:   {fit.evaluations}, converged: {fit.success}, applied: {fit.applied}")


if __name__ == "__main__":
    main()
