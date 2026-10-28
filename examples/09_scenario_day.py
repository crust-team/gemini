"""Run one day of assumed flow and ESP frequency on a finite hourly clock."""

from pathlib import Path

import gemini as gm

DATA = Path(__file__).resolve().parents[1] / "datasets/geothermal_doublet"
plant = gm.load_plant(DATA)

clock = gm.Clock.days(2027, 1, 1)
profiles = {
    "Qp": gm.Profile.constant(150, unit="m3/h", clock=clock),
    "ESP_freq": gm.Profile.constant(55, unit="Hz", clock=clock),
}
result = gm.Engine().simulate(plant, gm.Dataset.from_profiles(profiles), clock)
print(result.summary())
print("Secondary boundary defaults are explicit assumptions stored with this plant.")
