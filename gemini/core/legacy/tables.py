"""Convert GEMINI property snapshots to component parameters at the configuration edge."""

import csv
from pathlib import Path

from gemini.core.modules import (
    ESP,
    Degasser,
    Filter,
    HeatExchanger,
    InjectionPump,
    InjectionReservoir,
    InjectionWell,
    ProductionReservoir,
    ProductionWell,
)
from gemini.core.physics import geometry, units
from gemini.utils.files import read_json

# All old-format names are intentionally confined to the legacy package.
MODULE_TYPES = {
    "production_reservoir": ProductionReservoir,
    "injection_reservoir": InjectionReservoir,
    "production_well": ProductionWell,
    "injection_well": InjectionWell,
    "esp": ESP,
    "injection_pump": InjectionPump,
    "filter": Filter,
    "degasser": Degasser,
    "heat_exchanger": HeatExchanger,
}
TYPES = {
    "production_well": "production_well",
    "injection_well": "injection_well",
    "heat_exchanger": "heat_exchanger",
    "injection_pump": "injection_pump",
}
PORTS = {
    "production_reservoir": {"out": "sandface"},
    "injection_reservoir": {"in": "sandface"},
    "production_well": {"in": "bottom", "out": "wellhead"},
    "injection_well": {"in": "wellhead", "out": "bottom"},
    "esp": {"in": "suction", "out": "discharge"},
    "injection_pump": {"in": "suction", "out": "discharge"},
    "filter": {"in": "inlet", "out": "outlet"},
    "degasser": {"in": "inlet", "out1": "liquid", "out2": "gas"},
    "heat_exchanger": {
        "PrimIn": "hot_in",
        "PrimOut": "hot_out",
        "SecIn": "cold_in",
        "SecOut": "cold_out",
    },
}
NODE_PATHS = {
    "reservoir_c1b5": "doublet.reservoir",
    "production_well_c774": "doublet.well",
    "esp_1ee3": "doublet.esp",
    "degasser_e846": "degasser",
    "filter_b2e6": "filters.hot",
    "heat_exchanger_3410": "heat_exchanger",
    "filter_b1ed": "filters.cold",
    "injection_pump_3808": "injection_pump",
    "injection_well_a06b": "doublet.injector",
    "reservoir_28fc": "doublet.sink",
}


def _load_trajectory_csv(path):
    """Read the old semicolon trajectory schema at the legacy boundary."""
    with Path(path).open(newline="") as handle:
        return [
            {
                key: float(value) if key in {"MD", "TVD", "ID", "roughness"} else value
                for key, value in row.items()
            }
            for row in csv.DictReader(handle, delimiter=";")
        ]


def snapshot(properties: dict, index: int = 0) -> dict:
    """Extract one timestamp from a GEMINI property block without changing its values."""
    return {
        key: value[index] if isinstance(value, list) else value for key, value in properties.items()
    }


def read_property(path: str | Path, index: int = 0) -> dict:
    """Read an example .param file and return its scalar property snapshot."""
    return snapshot(read_json(path)["parameters"]["property"], index)


def _values(properties):
    # Raw GEMINI blocks store every property as a timestamp-indexed list.
    if properties and all(isinstance(v, list) for v in properties.values()):
        return snapshot(properties)
    return dict(properties)


def _coefficients(value):
    return list(map(float, value.split(";"))) if isinstance(value, str) else list(value)


def esp_params_from_gemini(property: dict) -> dict:
    """Convert ESP flow limits [m3/h] and VLP correction offset [bar] to SI parameters."""
    p = _values(property)
    correction = _coefficients(p.get("esp_correction_factor", "1;0"))
    return dict(
        no_stages=p["esp_no_stage"],
        head_coeff=_coefficients(p["esp_head_coeff"]),
        power_coeff=_coefficients(p["esp_power_coeff"]),
        pump_type=p.get("esp_type"),
        setting_depth=p.get("esp_depth", 0),
        min_flow=units.m3h_to_m3s(p.get("esp_min_flow", 0)),
        max_flow=units.m3h_to_m3s(p.get("esp_max_flow", 1e6)),
        bep_flow=units.m3h_to_m3s(p.get("esp_bep_flow", 1)),
        correction_factor=(correction[0], units.bar_to_pa(correction[1])),
        tubing=p.get("esp_tubing"),
    )


def reservoir_params_from_gemini(
    property: dict, well_property: dict | None = None, role: str = "production"
) -> dict:
    """Combine reservoir and well data; convert bar, degC, mD and m3/h/bar to SI."""
    p = _values(property)
    w = _values(well_property or {})
    result = dict(
        role=role,
        pressure=units.bar_to_pa(p["reservoir_pressure"]),
        temperature=units.c_to_k(p["reservoir_temperature"]),
        permeability=units.md_to_m2(p["reservoir_permeability"]),
        thickness=p["reservoir_thickness"],
        drainage_radius=p["reservoir_radius"],
        top_depth=p["reservoir_top"],
        wellbore_radius=w.get("wellbore_radius", p.get("wellbore_radius", 0.0765)),
        skin=p.get("skin", 0),
        liquid_density=p.get("liquid_density"),
        liquid_viscosity=p.get("liquid_viscosity"),
    )
    for key, prefix in [
        ("productivity_index", "productionwell"),
        ("injectivity_index", "injectionwell"),
    ]:
        value = w.get(f"{prefix}_{key}", p.get(key))
        result[key] = units.index_to_si(value) if value is not None else None
    return result


def production_reservoir_params_from_gemini(property: dict, well_property: dict) -> dict:
    """Map production-side reservoir and well property blocks to SI."""
    return reservoir_params_from_gemini(property, well_property, "production")


def injection_reservoir_params_from_gemini(property: dict, well_property: dict) -> dict:
    """Map injection-side reservoir and well property blocks to SI."""
    return reservoir_params_from_gemini(property, well_property, "injection")


def _well_params(properties, prefix, base_path):
    p = _values(properties)
    table = p.get(f"{prefix}_trajectory_table")
    if not table:
        filename = p.get(f"{prefix}_trajectory_file")
        if not filename:
            raise ValueError(f"{prefix}: provide a trajectory table or trajectory file")
        table = _load_trajectory_csv(Path(base_path) / filename)
    tally = []
    for row in p.get(f"{prefix}_tally_table", []):
        # WIMS tally ID is inches; trajectory ID and roughness are already metres.
        tally.append(dict(row, ID=units.inch_to_m(float(row["ID"]))))
    return dict(
        pipe_path=geometry.build_path(table, tally),
        friction_correlation=p.get(f"{prefix}_friction_correlation", "darcy_weisbach"),
        friction_correlation_2p=p.get(f"{prefix}_friction_correlation_2p", "BeggsBrill"),
        correction_factors=tuple(p.get(f"{prefix}_friction_correction_factors", (1, 0))),
        soil_temperature=units.c_to_k(p[f"{prefix}_soil_temperature"]),
        u_value=p.get("u_value", 10),
    )


def productionwell_params_from_gemini(
    property: dict, *, base_path: str | Path = ".", esp_property: dict | None = None
) -> dict:
    """Map production-well trajectory, tally and ambient temperature to SI."""
    params = _well_params(property, "productionwell", base_path)
    params["esp_depth"] = _values(esp_property or {}).get("esp_depth")
    return params


def injectionwell_params_from_gemini(property: dict, *, base_path: str | Path = ".") -> dict:
    """Map injection-well trajectory, tally and ambient temperature to SI."""
    return _well_params(property, "injectionwell", base_path)


def injectionpump_params_from_gemini(property: dict) -> dict:
    """Map injection-pump stages and equipment type [-]."""
    p = _values(property)
    return dict(no_stages=p["injectionpump_no_stage"], pump_type=p["injectionpump_type"])


def boosterpump_params_from_gemini(property: dict) -> dict:
    """Map the currently empty booster-pump property block."""
    return {}


def degasser_params_from_gemini(property: dict) -> dict:
    """Preserve the example degasser's otherwise unused heat-transfer parameter."""
    # NOTE(refactor): no legacy calculation establishes this coefficient's meaning or unit.
    return dict(heat_transfer_coeff=_values(property)["heat_transfer_coeff"])


def filter_params_from_gemini(property: dict) -> dict:
    """Map an optional filter clogging limit [bar] to [Pa]."""
    return dict(clogging_dp=units.bar_to_pa(_values(property).get("clogging_dp", 0.5)))


def blowdown_params_from_gemini(property: dict) -> dict:
    """Map the currently empty blowdown property block."""
    return {}


def boiler_params_from_gemini(property: dict) -> dict:
    """Map explicit boiler capacity [W], efficiency [-], and fuel [-]."""
    p = _values(property)
    return dict(fuel_type=p["fuel"], capacity=p["capacity"], efficiency=p["efficiency"])


# New derived class names retain the old file-schema spelling inside these converters.
production_well_params_from_gemini = productionwell_params_from_gemini
injection_well_params_from_gemini = injectionwell_params_from_gemini
injection_pump_params_from_gemini = injectionpump_params_from_gemini


def heatexchanger_params_from_gemini(property: dict) -> dict:
    """Interpret the legacy heat_transfer_coeff as lumped conductance UA [W/K]."""
    # NOTE(refactor): 100000 is plausible UA, but it is not calibrated to the example CSV.
    # Nominal pressure drops and mass rates must be supplied to predict hydraulic losses.
    p = _values(property)
    return dict(
        ua=p.get("ua", p.get("heat_transfer_coeff")),
        arrangement=p.get("arrangement", "counterflow"),
        dp_hot_nominal=p.get("dp_hot_nominal", 0),
        dp_cold_nominal=p.get("dp_cold_nominal", 0),
        m_dot_hot_nominal=p.get("m_dot_hot_nominal", 1),
        m_dot_cold_nominal=p.get("m_dot_cold_nominal", 1),
    )


heat_exchanger_params_from_gemini = heatexchanger_params_from_gemini
