"""Print the example reservoir's linear inflow performance relationship."""

from pathlib import Path

from gemini.components.subsurface import ProductionReservoir
from gemini.core.physics import units
from gemini.core.plant import param_mapping as mapping

DATA = Path(__file__).resolve().parents[1] / "datasets/geothermal_example"
params = mapping.production_reservoir_params_from_gemini(
    mapping.read_property(DATA / "reservoir_c1b5.param"),
    mapping.read_property(DATA / "production_well_c774.param"),
)
reservoir = ProductionReservoir(params)
rho = reservoir.fluid.properties(reservoir.params.pressure, reservoir.params.temperature).rho_l
print("Flow [m3/h]  Bottomhole [bar]  Drawdown [bar]")
for flow in (50, 100, 150):
    out, _ = reservoir.compute({"m_dot": units.m3h_to_m3s(flow) * rho}, {})
    print(
        f"{flow:11.1f}  {units.pa_to_bar(out.bottomhole_pressure):16.3f}"
        f"  {units.pa_to_bar(out.drawdown):14.3f}"
    )
