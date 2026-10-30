"""Compare one simulated day at three ESP frequencies.

Below about 52 Hz this pump cannot lift the produced brine to the surface and every step fails
with a negative pressure, so the sweep starts at 55 Hz and refuses to print a summary of failed
steps.

Run from the repository root: PYTHONPATH=. python examples/plants/simulate/00_esp_frequency_sweep.py
"""

import gemini as gm

plant = gm.Plant.load("examples/shared/doublet_heat/plant.json")
clock = gm.Clock.days(2027, 1, 1, days=1)
for frequency in (55, 60, 65):
    profiles = {
        "doublet.reservoir.production_rate": gm.Profile.constant(150, unit="m3/h", clock=clock),
        "doublet.esp.frequency": gm.Profile.constant(frequency, unit="Hz", clock=clock),
        "injection_pump.pressure_setpoint": gm.Profile.constant(51.5, unit="bar", clock=clock),
    }
    results = gm.simulate(plant, gm.Dataset.from_profiles(profiles), clock=clock)
    assert not results.errors(), results.errors()[0]
    print(frequency, results.to_frame(table="energy"))
