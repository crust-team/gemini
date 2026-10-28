"""Replay one week and display soft sensors and assessed health."""

from pathlib import Path

from gemini.core.config.build import build_plant
from gemini.core.config.gemini_loader import load_gemini
from gemini.core.data.timeseries import CSVTimeSeries
from gemini.core.modes.history import replay

DATA = Path(__file__).resolve().parents[1] / "datasets/geothermal_doublet"
config = load_gemini(DATA)
plant = build_plant(config)
measurements = CSVTimeSeries(DATA / "geothermal_example_dataset.csv").frame.iloc[: 7 * 96]
results = replay(plant, config, measurements)
frame = results.to_frame()
print(frame.loc[:, [("esp_1ee3", "head"), ("heat_exchanger_3410", "duty")]].head())
for name in config.bindings:
    assessed = bool(frame[name].health_assessed.all())
    print(f"{name}: assessed={assessed}, alarm rate={frame[name].health_alarm.mean():.1%}")
print("The supplied ESP curves disagree with measured head and contain no power coefficients.")
