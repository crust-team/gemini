"""Pass streams through a geothermal doublet with an explicit ESP and secondary heat loop."""

from pathlib import Path

from gemini.core.config import param_mapping as mapping
from gemini.core.modules.heat import HeatExchanger
from gemini.core.modules.pumps import ESP
from gemini.core.modules.subsurface import (
    InjectionReservoir,
    InjectionWell,
    ProductionReservoir,
    ProductionWell,
)
from gemini.core.physics import units
from gemini.core.types.flows import Stream
from gemini.core.types.fluid import WATER, Fluid

DATA = Path(__file__).resolve().parents[1] / "datasets/geothermal_doublet"


def read(name):
    """Load a property snapshot from the local example configuration."""
    return mapping.read_property(DATA / name)


def show(label, stream):
    """Display an SI stream with pressure and temperature converted at the output edge."""
    print(
        f"{label:20s} {stream.m_dot:8.3f} kg/s  {units.pa_to_bar(stream.p):9.3f} bar"
        f"  {units.k_to_c(stream.T):8.3f} degC"
    )


rp = read("reservoir_c1b5.param")
wp = read("production_well_c774.param")
ep = read("esp_1ee3.param")
brine = Fluid(liquid_density=rp["liquid_density"], liquid_viscosity=rp["liquid_viscosity"])
production = ProductionReservoir(
    mapping.production_reservoir_params_from_gemini(rp, wp), fluid=brine
)
well = ProductionWell(mapping.productionwell_params_from_gemini(wp, esp_property=ep), fluid=brine)
pump = ESP(mapping.esp_params_from_gemini(ep), fluid=brine)
hex_params = mapping.heatexchanger_params_from_gemini(read("heat_exchanger_3410.param"))
exchanger = HeatExchanger(hex_params)
injection = InjectionWell(
    mapping.injectionwell_params_from_gemini(read("injection_well_a06b.param")),
    fluid=brine,
)
receiving = InjectionReservoir(
    mapping.injection_reservoir_params_from_gemini(
        read("reservoir_28fc.param"), read("injection_well_a06b.param")
    ),
    fluid=brine,
)
_, streams = production({"m_dot": units.m3h_to_m3s(130) * rp["liquid_density"]}, {})
stream = streams["sandface"]
show("Reservoir sandface", stream)
stream = well.intake_conditions(stream)
show("ESP intake", stream)
_, streams = pump({"frequency": 60}, {"suction": stream})
stream = streams["discharge"]
show("ESP discharge", stream)
stream = well.wellhead_from_discharge(stream)
show("Production wellhead", stream)
secondary = Stream(
    m_dot=units.m3h_to_m3s(160) * 1000, T=units.c_to_k(20), p=units.bar_to_pa(5), fluid=WATER
)
show("Secondary inlet", secondary)
_, streams = exchanger({}, {"hot_in": stream, "cold_in": secondary})
stream = streams["hot_out"]
show("HEX primary outlet", stream)
show("HEX secondary outlet", streams["cold_out"])
_, streams = injection({}, {"wellhead": stream})
stream = streams["bottom"]
show("Injection sandface", stream)
out, _ = receiving({}, {"sandface": stream})
print(f"Required injection BHP: {units.pa_to_bar(out.bottomhole_pressure):.3f} bar")
print(
    "This is an imposed-flow chain; a network solver would balance the injection pressure residual."
)
