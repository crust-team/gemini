"""Old-format name tables and property converters, the only home of old GEMINI names.

The bridge maps exactly the example project: its ten old nodes (``NODE_PATHS``), its data CSV
columns (``SUPPLEMENTS``, ``EXTRA_COLUMNS``, ``ROOT_INLETS``) and its assumptions. Any other old
node set is rejected rather than guessed.
"""

import csv
import io
from pathlib import Path

from gemini.core.modules.heat import HeatExchanger
from gemini.core.modules.pumps import ESP, InjectionPump
from gemini.core.modules.subsurface import (
    InjectionReservoir,
    InjectionWell,
    ProductionReservoir,
    ProductionWell,
)
from gemini.core.modules.treatment import Degasser, Filter
from gemini.core.modules.treatment.filter import DEFAULT_CLOGGING_BAR
from gemini.core.physics import geometry, units
from gemini.errors import LegacyFormatError
from gemini.utils.files import read_json

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
RISERS = {"doublet.well": ("doublet.esp", "doublet.riser")}
"""Production wells split at their buried pump: well path -> (pump path, riser path above it)."""

SI_UNITS = {
    "bar": "Pa",
    "barg": "Pa",
    "degC": "K",
    "m3/h": "m3/s",
    "m3/s": "m3/s",
    "kg/s": "kg/s",
    "Hz": "Hz",
    "W": "W",
    "Pa": "Pa",
    "K": "K",
    "-": "-",
}
"""Units of old tags and the SI unit each converts to."""

_WELL_PROPERTIES = {
    "friction_correction_factors",
    "friction_correlation",
    "friction_correlation_2p",
    "soil_temperature",
    "tally_table",
    "trajectory_file",
    "trajectory_table",
}
_RESERVOIR_PROPERTIES = {
    "liquid_density",
    "liquid_viscosity",
    "reservoir_permeability",
    "reservoir_pressure",
    "reservoir_radius",
    "reservoir_temperature",
    "reservoir_thickness",
    "reservoir_top",
    "skin",
    "wellbore_radius",
    "productivity_index",
    "injectivity_index",
    "salinity",
    "co2_mass_fraction",
    "gas_mass_fraction",
}
PROPERTIES = {
    "esp": {
        "esp_bep_flow",
        "esp_correction_factor",
        "esp_depth",
        "esp_head_coeff",
        "esp_max_flow",
        "esp_min_flow",
        "esp_no_stage",
        "esp_power_coeff",
        "esp_tubing",
        "esp_type",
    },
    "production_reservoir": _RESERVOIR_PROPERTIES,
    "injection_reservoir": _RESERVOIR_PROPERTIES,
    "production_well": {f"productionwell_{key}" for key in _WELL_PROPERTIES}
    | {"productionwell_productivity_index", "wellbore_radius"},
    "injection_well": {f"injectionwell_{key}" for key in _WELL_PROPERTIES}
    | {"injectionwell_injectivity_index", "wellbore_radius"},
    "heat_exchanger": {
        "heat_transfer_coeff",
        "ua",
        "arrangement",
        "dp_hot_nominal",
        "dp_cold_nominal",
        "m_dot_hot_nominal",
        "m_dot_cold_nominal",
    },
    "degasser": {"heat_transfer_coeff"},
    "filter": {"clogging_dp"},
    "injection_pump": {"injectionpump_no_stage", "injectionpump_type"},
}
"""Old properties each node kind converts; anything else is reported as unmapped."""

TAGS = {
    "esp": {
        "esp_frequency": ("controls.frequency", "Hz"),
        "esp_flow": ("inlets.suction.m_dot", "m3/h"),
        "esp_inlet_pressure": ("inlets.suction.p", "bar"),
        "esp_inlet_temperature": ("inlets.suction.T", "degC"),
        "esp_head": ("measured.head", "bar"),
        "esp_outlet_pressure": ("measured.discharge_pressure", "bar"),
        "esp_power_consumption": ("measured.power", "W"),
    },
    "filter": {
        "filter_flow": ("inlets.inlet.m_dot", "m3/h"),
        "filter_inlet_pressure": ("inlets.inlet.p", "bar"),
        "filter_inlet_temperature": ("inlets.inlet.T", "degC"),
    },
    "degasser": {
        "degasser_inlet_flow": ("inlets.inlet.m_dot", "m3/h"),
        "degasser_pressure": ("inlets.inlet.p", "bar"),
    },
    "injection_pump": {
        "injectionpump_flow": ("inlets.suction.m_dot", "m3/h"),
        "injectionpump_inlet_pressure": ("inlets.suction.p", "bar"),
        "injectionpump_inlet_temperature": ("inlets.suction.T", "degC"),
        "injectionpump_outlet_pressure": ("controls.pressure_setpoint", "bar"),
        "injectionpump_power_consumption": ("measured.power", "W"),
        "injectionpump_frequency": ("controls.frequency", "Hz"),
        "injectionpump_head": ("measured.head", "bar"),
    },
    "injection_well": {
        "injectionwell_flow": ("inlets.wellhead.m_dot", "m3/h"),
        "injectionwell_wellhead_pressure": ("inlets.wellhead.p", "bar"),
        "injectionwell_wellhead_temperature": ("inlets.wellhead.T", "degC"),
        "injectionwell_bottomhole_pressure": ("measured.bottomhole_pressure", "bar"),
        "injectionwell_bottomhole_temperature": ("measured.bottomhole_temperature", "degC"),
    },
    "heat_exchanger": {
        "hex_primary_flow": ("inlets.hot_in.m_dot", "m3/h"),
        "hex_primary_inlet_pressure": ("inlets.hot_in.p", "bar"),
        "hex_primary_inlet_temperature": ("inlets.hot_in.T", "degC"),
        "hex_primary_outlet_temperature": ("measured.hot_out_T", "degC"),
        "hex_secondary_flow": ("inlets.cold_in.m_dot", "m3/h"),
        "hex_secondary_inlet_pressure": ("inlets.cold_in.p", "bar"),
        "hex_secondary_inlet_temperature": ("inlets.cold_in.T", "degC"),
        "hex_secondary_outlet_temperature": ("measured.cold_out_T", "degC"),
    },
}
"""Measured old tags per node kind: binding target ``<section>.<name>[.<field>]`` and unit."""

_NO_SANDFACE = "No measured sandface boundary: this well is evaluated in the chained scenario only."
IGNORED_TAGS = {
    "esp_outlet_temperature": "Isothermal pump model has no outlet-temperature output.",
    "filter_outlet_pressure": "Pressure loss uses the explicit PDrop CSV column instead.",
    "filter_outlet_temperature": "Isothermal filter has no temperature diagnostic.",
    "degasser_outlet_liquid_flow": "Duplicates Qp; the liquid-only model conserves inlet mass.",
    "injectionpump_outlet_temperature": "Isothermal pump model has no outlet-temperature output.",
    "hex_primary_outlet_pressure": "Hydraulic measurement represented by HEX_PDrop.",
    "hex_secondary_outlet_pressure": "No measured secondary pressure loss in this dataset.",
    "productionwell_flow": _NO_SANDFACE,
    "productionwell_wellhead_pressure": _NO_SANDFACE,
    "productionwell_wellhead_temperature": _NO_SANDFACE,
}
"""Measured old tags deliberately left unbound, with the reason."""

SUPPLEMENTS = {
    "degasser": [("inlets.inlet.T", "T_p_in", "degC")],
    "heat_exchanger": [
        ("measured.duty", "Thermal_PowerGen", "W"),
        ("measured.dp_hot", "HEX_PDrop", "bar"),
    ],
    "production_reservoir": [("controls.production_rate", "Qp", "m3/h")],
}
"""Dataset channels the project tags omit, bound only when the data CSV has the column.

NOTE(refactor): project tags omit these CSV channels and secondary absolute pressure.
Supplements are explicit, dataset-specific, and applied only when the columns exist. Filters
also bind their pressure drop from the ``_PDrop`` column next to their ``_Pin`` tag.
"""

EXTRA_COLUMNS = {"Pwh_prod": ("production_wellhead_pressure", "bar")}
"""Unbound data CSV columns that ``to_dataset`` keeps, converted to SI: old -> (new, unit)."""

ROOT_INLETS = {"secondary_in": {"m_dot": ("Qs", "m3/h"), "T": ("T_s_in", "degC")}}
"""Data CSV columns of the plant's secondary inlet: field -> (column, unit)."""

ASSUMED_SECONDARY_PRESSURE = 5e5
"""Unmeasured secondary inlet pressure [Pa], 5 bar absolute."""

INJECTION_SETPOINT = 5.15e6
"""Injection-pump scenario discharge setpoint [Pa]."""

PARAMETER_SUPPLEMENTS = {"injection_pump": ("InjectorPump_PowerDraw", {"efficiency": 0.8})}
"""Parameters a data CSV column implies but the old project lacks: kind -> (column, params).

NOTE(refactor): example Q*deltaP/PowerDraw is 0.80000 (within rounding). No curves exist, so
use the pressure-setpoint variant with efficiency 0.8; the standalone equipment default stays
0.7.
"""

STREAM_DEFAULTS = {"heat_exchanger": {"cold_in": {"p": ASSUMED_SECONDARY_PRESSURE}}}
"""Inlet values assumed per node kind when the data CSV has no column for them."""

SCENARIO_INPUTS = {"injection_pump": {"pressure_setpoint": INJECTION_SETPOINT}}
"""Controls per node kind for scenarios.

NOTE(refactor): no injection curves are supplied; the twin uses the measured discharge
setpoint. The example efficiency is explicit in the snapshot; no curve is fabricated.
"""

EXAMPLE_BULK_HEAT_CAPACITY = 4.410e6
"""Volumetric heat capacity [J/m3/K] inferred from the example heat balance."""

ROOT_DEFAULTS = {"secondary_in": {"m_dot": 40, "T": 293.15, "p": ASSUMED_SECONDARY_PRESSURE}}
"""Plant inlets assumed by simulations without their measurements: kg/s, K, Pa.

NOTE(refactor): two-control simulations need an assumed secondary boundary. Store 40 kg/s,
20 C and 5 bar explicitly; measured replay never uses these defaults.
"""

TRACE_CONTROLS = {
    "doublet.reservoir.production_rate": 40.0,
    "doublet.esp.frequency": 60.0,
    "injection_pump.pressure_setpoint": INJECTION_SETPOINT,
}
"""Controls used to run one traced step of a converted plant in ``check_wiring``."""

FALLBACK_LIQUID_DENSITY = 1000
"""Brine density [kg/m3] when the production reservoir gives none."""

FALLBACK_LIQUID_VISCOSITY = 0.001
"""Brine viscosity [Pa.s] when the production reservoir gives none."""

HEAT_BALANCE_COLUMNS = {"Thermal_PowerGen", "Qp", "T_p_in", "T_p_out"}
"""Data CSV columns from which the example bulk heat capacity was inferred."""

HEAT_BALANCE_ASSUMPTIONS = [
    "Example bulk heat capacity 4.410 MJ/m3/K inferred from its heat balance.",
    "Unmeasured secondary inlet pressure assumed 5 bar absolute.",
    "Injection-pump scenario setpoint 51.5 bar; twin uses measured setpoint.",
]
ROOT_ASSUMPTION = "Profiles lacking secondary measurements assume 40 kg/s at 20 C and 5 bar."

PROPERTY_OWNERS = {
    ("doublet.well", "productionwell_productivity_index"): "doublet.reservoir",
    ("doublet.well", "wellbore_radius"): "doublet.reservoir",
    ("doublet.injector", "injectionwell_injectivity_index"): "doublet.sink",
    ("doublet.injector", "wellbore_radius"): "doublet.sink",
}
"""Old well properties whose new parameter lives on the adjacent reservoir: (path, name) -> path."""

PROPERTY_INVERSE = {
    "esp_depth": ("setting_depth", None),
    "esp_no_stage": ("no_stages", None),
    "esp_tubing": ("tubing", None),
    "esp_type": ("pump_type", None),
    "esp_bep_flow": ("bep_flow", units.m3s_to_m3h),
    "esp_min_flow": ("min_flow", units.m3s_to_m3h),
    "esp_max_flow": ("max_flow", units.m3s_to_m3h),
    "injectionpump_no_stage": ("no_stages", None),
    "injectionpump_type": ("pump_type", None),
    "reservoir_thickness": ("thickness", None),
    "reservoir_radius": ("drainage_radius", None),
    "reservoir_top": ("top_depth", None),
    "reservoir_pressure": ("pressure", units.pa_to_bar),
    "reservoir_temperature": ("temperature", units.k_to_c),
    "reservoir_permeability": ("permeability", units.m2_to_md),
    "liquid_density": ("liquid_density", None),
    "liquid_viscosity": ("liquid_viscosity", None),
    "skin": ("skin", None),
    "wellbore_radius": ("wellbore_radius", None),
}
"""Old property -> (new parameter, conversion from SI or None)."""

SUFFIX_INVERSE = [
    ("_soil_temperature", "soil_temperature", units.k_to_c),
    ("_friction_correlation", "friction_correlation", None),
    ("_friction_correlation_2p", "friction_correlation_2p", None),
    ("_friction_correction_factors", "correction_factors", list),
    ("_productivity_index", "productivity_index", units.index_from_si),
    ("_injectivity_index", "injectivity_index", units.index_from_si),
]
"""Well properties named ``<prefix><suffix>``: suffix -> (new parameter, conversion)."""

COEFFICIENT_PROPERTIES = {"esp_head_coeff": "head_coeff", "esp_power_coeff": "power_coeff"}
"""Old ``;``-separated coefficient lists -> new list parameters."""


def parse_coefficients(value):
    """Return old coefficients, a ``;``-separated string or a list, as a list of floats."""
    return list(map(float, value.split(";"))) if isinstance(value, str) else list(value)


def parse_trajectory_csv(text):
    """Parse the old semicolon trajectory schema; depths, ID and roughness are metres."""
    return [
        {
            key: float(value) if key in {"MD", "TVD", "ID", "roughness"} else value
            for key, value in row.items()
        }
        for row in csv.DictReader(io.StringIO(text, newline=""), delimiter=";")
    ]


def read_property(path: str | Path, index: int = 0) -> dict:
    """Read an example .param file and return its property snapshot at timestamp ``index``."""
    properties = read_json(path)["parameters"]["property"]
    return {
        key: value[index] if isinstance(value, list) else value for key, value in properties.items()
    }


def esp_params_from_gemini(properties: dict) -> dict:
    """Convert ESP flow limits [m3/h] and VLP correction offset [bar] to SI parameters."""
    correction = parse_coefficients(properties.get("esp_correction_factor", "1;0"))
    return dict(
        no_stages=properties["esp_no_stage"],
        head_coeff=parse_coefficients(properties["esp_head_coeff"]),
        power_coeff=parse_coefficients(properties["esp_power_coeff"]),
        pump_type=properties.get("esp_type"),
        setting_depth=properties.get("esp_depth", 0),
        min_flow=units.m3h_to_m3s(properties.get("esp_min_flow", 0)),
        max_flow=units.m3h_to_m3s(properties.get("esp_max_flow", 1e6)),
        bep_flow=units.m3h_to_m3s(properties.get("esp_bep_flow", 1)),
        correction_factor=(correction[0], units.bar_to_pa(correction[1])),
        tubing=properties.get("esp_tubing"),
    )


def reservoir_params_from_gemini(
    properties: dict, well_property: dict | None = None, role: str = "production"
) -> dict:
    """Combine reservoir and well data; convert bar, degC, mD and m3/h/bar to SI."""
    well = well_property or {}
    result = dict(
        role=role,
        pressure=units.bar_to_pa(properties["reservoir_pressure"]),
        temperature=units.c_to_k(properties["reservoir_temperature"]),
        permeability=units.md_to_m2(properties["reservoir_permeability"]),
        thickness=properties["reservoir_thickness"],
        drainage_radius=properties["reservoir_radius"],
        top_depth=properties["reservoir_top"],
        wellbore_radius=well.get("wellbore_radius", properties.get("wellbore_radius", 0.0765)),
        skin=properties.get("skin", 0),
        liquid_density=properties.get("liquid_density"),
        liquid_viscosity=properties.get("liquid_viscosity"),
    )
    for key, prefix in [
        ("productivity_index", "productionwell"),
        ("injectivity_index", "injectionwell"),
    ]:
        value = well.get(f"{prefix}_{key}", properties.get(key))
        result[key] = units.index_to_si(value) if value is not None else None
    return result


def production_reservoir_params_from_gemini(properties: dict, well_property: dict) -> dict:
    """Map production-side reservoir and well property blocks to SI."""
    return reservoir_params_from_gemini(properties, well_property, "production")


def injection_reservoir_params_from_gemini(properties: dict, well_property: dict) -> dict:
    """Map injection-side reservoir and well property blocks to SI."""
    return reservoir_params_from_gemini(properties, well_property, "injection")


def _well_params(properties, prefix, base_path):
    """Map a well trajectory, tally and ambient temperature to SI.

    The trajectory comes from the inline table or, when that is empty, from the named file
    below ``base_path``. Old tally IDs are inches; trajectory ID and roughness are metres.
    """
    table = properties.get(f"{prefix}_trajectory_table")
    if not table:
        filename = properties.get(f"{prefix}_trajectory_file")
        if not filename:
            raise LegacyFormatError(f"{prefix}: provide a trajectory table or trajectory file")
        text = (Path(base_path) / filename).read_text(encoding="utf-8-sig")
        table = parse_trajectory_csv(text)
    tally = [
        dict(row, ID=units.inch_to_m(float(row["ID"])))
        for row in properties.get(f"{prefix}_tally_table", [])
    ]
    return dict(
        pipe_path=geometry.build_path(table, tally),
        friction_correlation=properties.get(f"{prefix}_friction_correlation", "darcy_weisbach"),
        friction_correlation_2p=properties.get(f"{prefix}_friction_correlation_2p", "BeggsBrill"),
        correction_factors=tuple(properties.get(f"{prefix}_friction_correction_factors", (1, 0))),
        soil_temperature=units.c_to_k(properties[f"{prefix}_soil_temperature"]),
        u_value=properties.get("u_value", 10),
    )


def productionwell_params_from_gemini(
    properties: dict, *, base_path: str | Path = ".", esp_property: dict | None = None
) -> dict:
    """Map production-well trajectory, tally and ambient temperature to SI."""
    params = _well_params(properties, "productionwell", base_path)
    params["esp_depth"] = (esp_property or {}).get("esp_depth")
    return params


def injectionwell_params_from_gemini(properties: dict, *, base_path: str | Path = ".") -> dict:
    """Map injection-well trajectory, tally and ambient temperature to SI."""
    return _well_params(properties, "injectionwell", base_path)


def injectionpump_params_from_gemini(properties: dict) -> dict:
    """Map injection-pump stages and equipment type [-]."""
    return dict(
        no_stages=properties["injectionpump_no_stage"], pump_type=properties["injectionpump_type"]
    )


def degasser_params_from_gemini(properties: dict) -> dict:
    """Preserve the example degasser's otherwise unused heat-transfer parameter.

    NOTE(refactor): no legacy calculation establishes this coefficient's meaning or unit. It is
    kept as metadata; the liquid-only passthrough has no gas or thermal model.
    """
    return dict(heat_transfer_coeff=properties["heat_transfer_coeff"])


def filter_params_from_gemini(properties: dict) -> dict:
    """Map an optional filter clogging limit [bar] to [Pa]."""
    return dict(clogging_dp=units.bar_to_pa(properties.get("clogging_dp", DEFAULT_CLOGGING_BAR)))


def heatexchanger_params_from_gemini(properties: dict) -> dict:
    """Interpret the legacy heat_transfer_coeff as lumped conductance UA [W/K].

    NOTE(refactor): 100000 is plausible UA, but it is not calibrated to the example CSV.
    Nominal pressure drops and mass rates must be supplied to predict hydraulic losses.
    """
    return dict(
        ua=properties.get("ua", properties.get("heat_transfer_coeff")),
        arrangement=properties.get("arrangement", "counterflow"),
        dp_hot_nominal=properties.get("dp_hot_nominal", 0),
        dp_cold_nominal=properties.get("dp_cold_nominal", 0),
        m_dot_hot_nominal=properties.get("m_dot_hot_nominal", 1),
        m_dot_cold_nominal=properties.get("m_dot_cold_nominal", 1),
    )


CONVERTERS = {
    "esp": esp_params_from_gemini,
    "filter": filter_params_from_gemini,
    "degasser": degasser_params_from_gemini,
    "heat_exchanger": heatexchanger_params_from_gemini,
    "injection_pump": injectionpump_params_from_gemini,
}
"""Converters of node kinds that need no neighbouring node's properties."""

MODULE_CLASSES = {
    "esp": ESP,
    "filter": Filter,
    "degasser": Degasser,
    "heat_exchanger": HeatExchanger,
    "injection_pump": InjectionPump,
    "production_reservoir": ProductionReservoir,
    "injection_reservoir": InjectionReservoir,
    "production_well": ProductionWell,
    "injection_well": InjectionWell,
}
"""Module class each old node kind converts to."""
