"""Print the passive production-well pressure and temperature section profiles."""

from pathlib import Path

from gemini.components.subsurface import ProductionWell
from gemini.core.base.stream import Stream
from gemini.core.physics import units
from gemini.core.plant import param_mapping as mapping

DATA = Path(__file__).resolve().parents[1] / "datasets/geothermal_example"
well = ProductionWell(
    mapping.productionwell_params_from_gemini(
        mapping.read_property(DATA / "production_well_c774.param")
    )
)
bottom = Stream(m_dot=40, p=units.bar_to_pa(250), T=units.c_to_k(80))
out, _ = well.compute({}, {"bottom": bottom})
print("Traversed section  Pressure [bar]  Temperature [degC]")
for index, (p, T) in enumerate(zip(out.section_pressure, out.section_temperature), 1):
    print(f"{index:17d}  {units.pa_to_bar(p):14.3f}  {units.k_to_c(T):18.3f}")
