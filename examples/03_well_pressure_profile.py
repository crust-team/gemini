"""Print pressure and temperature profiles below the buried ESP."""

from pathlib import Path

import gemini as gm

DATA = Path(__file__).resolve().parents[1] / "datasets/geothermal_doublet"
plant = gm.load_plant(DATA)

well = plant.doublet.well
bottom = gm.Stream(m_dot=40, p=25e6, T=353.15, fluid=well.fluid)
out, _ = well(bottom=bottom)
print("Traversed section  Pressure [bar]  Temperature [degC]")
for index, (p, temperature) in enumerate(zip(out.section_pressure, out.section_temperature), 1):
    print(f"{index:17d}  {p / 1e5:14.3f}  {temperature - 273.15:18.3f}")
