"""Print the example reservoir inflow performance relationship."""

from pathlib import Path

import gemini as gm

DATA = Path(__file__).resolve().parents[1] / "datasets/geothermal_doublet"
plant = gm.load_plant(DATA)

reservoir = plant.doublet.reservoir
rho = reservoir.fluid.properties(reservoir.params.pressure, reservoir.params.temperature).density
print("Flow [m3/h]  Bottomhole [bar]  Drawdown [bar]")
for flow in (50, 100, 150):
    out, _ = reservoir({"m_dot": flow / 3600 * rho})
    print(f"{flow:11.1f}  {out.bottomhole_pressure / 1e5:16.3f}  {out.drawdown / 1e5:14.3f}")
