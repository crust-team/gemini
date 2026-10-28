"""Run 24 hourly chained steps using constant measured operating controls and inlet conditions."""

from pathlib import Path

from gemini.core.config.build import build_plant
from gemini.core.config.gemini_loader import load_gemini
from gemini.core.data.timeseries import CSVTimeSeries
from gemini.core.modes import history, scenario, twin

DATA = Path(__file__).resolve().parents[1] / "datasets/geothermal_doublet"
config = load_gemini(DATA)
plant = build_plant(config)
data = CSVTimeSeries(DATA / "geothermal_example_dataset.csv").frame
history.calibrate(plant, config, data.iloc[: 7 * 96], "heat_exchanger_3410", ["ua"], apply=True)
inputs, streams = twin.scenario_inputs(plant, data.iloc[0])
results = scenario.run(plant, [inputs | {"streams_in": streams}] * 24, dt=3600)
print(
    results.to_frame().loc[
        :, [("production_well_c774_riser", "wellhead_pressure"), ("heat_exchanger_3410", "duty")]
    ]
)
print(
    "Imposed flow; the supplied pressure and temperature design data do not match all measurements."
)
