"""Fit HX conductance on the first seven days and inspect the untouched holdout period."""

from pathlib import Path

from gemini.core.config.build import build_plant
from gemini.core.config.gemini_loader import load_gemini
from gemini.core.data.timeseries import CSVTimeSeries
from gemini.core.modes import history, twin

DATA = Path(__file__).resolve().parents[1] / "datasets/geothermal_doublet"
config = load_gemini(DATA)
plant = build_plant(config)
data = CSVTimeSeries(DATA / "geothermal_example_dataset.csv").frame
fit = history.calibrate(
    plant, config, data.iloc[: 7 * 96], "heat_exchanger_3410", ["ua"], apply=True
)
print(
    f"UA: {fit.fitted['ua']:.0f} W/K; normalised RMS: {fit.rms_before:.6f} -> {fit.rms_after:.6f}"
)
at, row = data.index[7 * 96], data.iloc[7 * 96]
result, health = twin.evaluate(plant, row, at)["heat_exchanger_3410"]
print(f"First holdout duty: {result.outputs.duty:.0f} W; measured {row.Thermal_PowerGen:.0f} W")
print(health.message)
