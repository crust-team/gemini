"""Compare one-day ESP frequencies. Run: python examples/core/simulate/00_esp_frequency_sweep.py."""

import gemini as gm
from examples.shared.doublet_heat.plant import DoubletHeatPlant

plant = DoubletHeatPlant.load("examples/shared/doublet_heat/plant.json")
clock = gm.Clock.days(2027, 1, 1, days=1)
for frequency in (45, 55, 65):
    profiles = {
        "doublet.reservoir.production_rate": gm.Profile.constant(150, unit="m3/h", clock=clock),
        "doublet.esp.frequency": gm.Profile.constant(frequency, unit="Hz", clock=clock),
        "injection_pump.pressure_setpoint": gm.Profile.constant(51.5, unit="bar", clock=clock),
    }
    results = gm.Engine().simulate(plant, gm.Dataset.from_profiles(profiles), clock=clock)
    print(frequency, results.summary())
