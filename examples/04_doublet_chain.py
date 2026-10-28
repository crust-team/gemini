"""Traverse the explicit doublet and surface-equipment chain."""

from pathlib import Path

import gemini as gm

DATA = Path(__file__).resolve().parents[1] / "datasets/geothermal_doublet"
plant = gm.load_plant(DATA)

result = plant(
    {
        "m_dot": 40,
        "esp_frequency": 60,
        "injection_pressure": 5.15e6,
        "secondary": gm.Stream(m_dot=40, T=293.15, p=5e5, fluid=gm.WATER),
    }
)
for path, child in plant.last_results.items():
    print(path, child.outputs)
print(gm.modules.collect_flows(result))
