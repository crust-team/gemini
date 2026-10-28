"""Print pump performance at three frequencies."""

from pathlib import Path

import gemini as gm

DATA = Path(__file__).resolve().parents[1] / "datasets/geothermal_doublet"
plant = gm.load_plant(DATA)

pump = plant.doublet.esp
suction = gm.Stream(m_dot=130 / 3600 * 1000, T=353.15, p=6e6)
print("Frequency [Hz]  Head [bar]  Power [W]  Efficiency [-]")
for frequency in (40, 50, 60):
    out, _ = pump({"frequency": frequency}, suction=suction)
    print(f"{frequency:14.0f}  {out.head / 1e5:10.3f}  {out.power:9.2f}  {out.efficiency:.4f}")
print("The example has zero power coefficients, so power and efficiency are zero.")
