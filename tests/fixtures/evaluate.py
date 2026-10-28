"""Evaluate immutable phase-0 cases through the new public component and physics APIs."""

import json
from pathlib import Path

from gemini.core.modules.pumps import ESP
from gemini.core.modules.subsurface import (
    InjectionReservoir,
    InjectionWell,
    ProductionReservoir,
    ProductionWell,
)
from gemini.core.physics import (
    chemistry,
    corrosion,
    erosion,
    geometry,
    heat_transfer,
    hydraulics,
    units,
)
from gemini.core.types.flows import Stream


def evaluate():
    """Return all phase-0 outputs in their original names and units for comparison."""
    cases = json.loads(Path(__file__).with_name("golden_values.json").read_text())
    actual = {}
    for name, case in cases.items():
        p = case.get("parameters", {})
        u = case["inputs"]
        if name.startswith("esp_"):
            output = ESP(**p)(
                frequency=u["pump_freq"],
                suction=Stream(m_dot=u["pump_flow"] * 1000, T=300, p=1e5),
            ).outputs
            result = dict(
                pump_head=output.head, pump_power=output.power, pump_eff=output.efficiency * 100
            )
        elif name.startswith("ipr_") or name in {
            "injectivity",
            "reservoir_estimate",
            "reservoir_dp",
        }:
            params = dict(
                pressure=22e6,
                temperature=353.15,
                permeability=units.md_to_m2(10000),
                thickness=45,
                drainage_radius=1000,
                top_depth=1800,
                wellbore_radius=0.0765,
                productivity_index=units.index_to_si(21),
                injectivity_index=units.index_to_si(20),
            )
            if name == "ipr_injection":
                c = InjectionReservoir(**params)
                out = c(sandface=Stream(m_dot=u["flow"] * 1000, T=300, p=23e6)).outputs
                result = dict(bottomhole_pressure=out.bottomhole_pressure)
            elif name == "ipr_production":
                out = ProductionReservoir(**params)(m_dot=u["flow"] * 1000).outputs
                result = dict(bottomhole_pressure=out.bottomhole_pressure)
            elif name == "injectivity":
                result = dict(
                    injectivity_index=InjectionReservoir(**params).injectivity_from_measurements(
                        u["flow"], u["bottomhole_pressure"]
                    )
                )
            elif name == "reservoir_estimate":
                pressure, r2 = ProductionReservoir.estimate_pressure(
                    u["flow"], u["bottomhole_pressure"]
                )
                result = dict(reservoir_pressure=pressure, r_squared=r2)
            else:
                params.update(
                    liquid_density=u["density"],
                    liquid_viscosity=u["viscosity"],
                    skin=u["skin_factor"],
                )
                out = ProductionReservoir(**params)(m_dot=u["flow"] * u["density"]).outputs
                result = dict(
                    Hydrostatic_dp=out.hydrostatic_dp,
                    skin_dp=out.skin_dp,
                    bottomhole_dp=out.flow_dp,
                    reservoir_dp=out.radial_bottomhole_pressure,
                )
        elif name.startswith("well_"):
            path = geometry.PipePath(
                sections=[
                    geometry.PipeSection(
                        length=length, inclination=a, inner_diameter=d, roughness=r
                    )
                    for length, a, d, r in zip(
                        p["length"], p["angle"], p["diameter"], p["roughness"]
                    )
                ]
            )
            stream = Stream(m_dot=u["flowrate"] * 1000, p=u["pressure"], T=u["temperature"])
            cls, port = (
                (ProductionWell, "bottom")
                if name == "well_production"
                else (InjectionWell, "wellhead")
            )
            evaluated = cls(pipe_path=path, soil_temperature=u["temperature_ambient"])(
                **{port: stream}
            )
            output = evaluated.outputs
            stream = next(
                value for value in evaluated.outlets.values() if isinstance(value, Stream)
            )
            result = dict(
                pressure_output=stream.p,
                temperature_output=stream.T,
                pressuredrop_fric_output=output.dp_friction,
                pressuredrop_grav_output=output.dp_gravity,
                section_pressure_output=output.section_pressure,
                section_temperature_output=output.section_temperature,
            )
        elif name == "darcy":
            result = hydraulics.darcy_weisbach_dp(*u)
        elif name == "beggs":
            result = hydraulics.beggs_brill_dp(*u)
        elif name == "temperature":
            result = heat_transfer.pipe_temperature_change(
                u[0], u[1], u[6], u[2], u[3], u[4], u[5], u[7]
            )
        elif name.startswith("corrosion_"):
            value = corrosion.co2_corrosion_rate(
                p["corrosion_model"],
                fitted=name.endswith("True"),
                temperature=units.c_to_k(u["temperature"]),
                pressure=units.bar_to_pa(u["pressure"]),
                water_flow_rate=u["flow_rate"],
                water_density=u["water_density"],
                water_viscosity=units.cp_to_pas(u["water_viscosity"]),
                diameter=p["diameter"],
                roughness=p["roughness"],
                co2_fraction=u["co2_fraction"],
                bicarb_concentration=units.mgl_to_kgm3(u["bicarb_concentration"]),
                ionic_strength=u["ionic_strength"],
            )
            result = dict(corrosion_rate=value)
        elif name == "chemistry":
            value = chemistry.co2_partial_pressure(
                co2_fraction=u["co2_mol_fraction"],
                gas_pressure=units.bar_to_pa(u["gas_pressure"]),
                gas_water_ratio=u["gas_water_ratio"],
                gas_density=u["gas_density"],
                gas_molecular_weight=u["gas_molecular_weight"] / 1000,
                temperature_sample=units.c_to_k(u["temperature_sample"]),
                temperature_system=units.c_to_k(u["temperature_system"]),
            )
            result = {"CO2 Partial Pressure [bar]": units.pa_to_bar(value)}
        elif name.startswith("erosion_"):
            model = p["erosion_model"]
            result = dict(erosion_rate_mm_yr=None, erosion_velocity_ms=None)
            if model == "API":
                result["erosion_velocity_ms"] = erosion.api_erosional_velocity(u["rho_fluid"])
            else:
                result["erosion_rate_mm_yr"] = erosion.erosion_rate(
                    model,
                    flow_rate=units.m3h_to_m3s(u["flowRate"]),
                    rho_fluid=u["rho_fluid"],
                    diameter=u["diameter"],
                )
        else:
            raise AssertionError(f"Uncovered golden case {name}")
        actual[name] = {"expected": result}
    return actual
