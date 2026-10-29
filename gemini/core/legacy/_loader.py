"""Import GEMINI projects with explicit parameter, port and sensor-tag accounting."""

import csv
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator

from gemini.core.types.bindings import (
    Binding,
    ConfigModel,
    DatedParams,
    ModuleBindings,
)
from gemini.core.types.fluid import BRINE, Fluid
from gemini.utils.files import read_json
from gemini.utils.mappings import set_nested
from gemini.utils.time import to_utc

from . import tables as mapping
from .tables import NODE_PATHS, TYPES


class ModuleDesign(ConfigModel):
    """Internal converted equipment design used only by the legacy bridge."""

    type: str
    params: list[DatedParams] = Field(min_length=1)
    fluid: Fluid = BRINE

    @field_validator("params")
    @classmethod
    def sort_snapshots(cls, values):
        """Order snapshots and reject duplicate effective dates."""
        dates = [item.valid_from for item in values]
        if len(set(dates)) != len(dates):
            raise ValueError("Duplicate parameter effective dates")
        return sorted(
            values, key=lambda item: item.valid_from or datetime.min.replace(tzinfo=timezone.utc)
        )

    def at(self, at=None):
        """Return the latest applicable snapshot."""
        eligible = [
            item
            for item in self.params
            if at is None or item.valid_from is None or item.valid_from <= to_utc(at)
        ]
        if not eligible:
            raise ValueError(f"{self.type}: no parameters valid at {at}")
        return eligible[-1]


class LegacyDesign(ConfigModel):
    """Internal interpretation of old files before applying them to a new plant."""

    name: str
    modules: dict[str, ModuleDesign]
    bindings: dict[str, ModuleBindings] = Field(default_factory=dict)
    boundary: dict[str, Any] = Field(default_factory=dict)
    timestep: float = Field(900, gt=0)
    ignored: dict[str, str] = Field(default_factory=dict)
    unmapped: list[str] = Field(default_factory=list)


PROPERTIES = {
    "esp": set(
        (
            "esp_bep_flow esp_correction_factor esp_depth esp_head_coeff esp_max_flow "
            "esp_min_flow esp_no_stage esp_power_coeff esp_tubing esp_type"
        ).split()
    ),
    "reservoir": set(
        (
            "liquid_density liquid_viscosity reservoir_permeability reservoir_pressure "
            "reservoir_radius reservoir_temperature reservoir_thickness reservoir_top skin"
            " wellbore_radius productivity_index injectivity_index "
            "salinity co2_mass_fraction gas_mass_fraction"
        ).split()
    ),
    "heat_exchanger": set(
        (
            "heat_transfer_coeff ua arrangement dp_hot_nominal dp_cold_nominal "
            "m_dot_hot_nominal m_dot_cold_nominal"
        ).split()
    ),
    "degasser": {"heat_transfer_coeff"},
    "filter": {"clogging_dp"},
    "injection_pump": {"injectionpump_no_stage", "injectionpump_type"},
}
for _kind, _prefix in (("production_well", "productionwell"), ("injection_well", "injectionwell")):
    PROPERTIES[_kind] = {
        f"{_prefix}_{key}"
        for key in (
            "friction_correction_factors",
            "friction_correlation",
            "friction_correlation_2p",
            "soil_temperature",
            "tally_table",
            "trajectory_file",
            "trajectory_table",
            "productivity_index" if _prefix == "productionwell" else "injectivity_index",
        )
    }
    PROPERTIES[_kind].add("wellbore_radius")

# Each target is inputs.field, streams.port.field, or measured.output.
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
IGNORED_TAGS = {
    "esp_outlet_temperature": "Isothermal pump model has no outlet-temperature output.",
    "filter_outlet_pressure": "Pressure loss uses the explicit PDrop CSV column instead.",
    "filter_outlet_temperature": "Isothermal filter has no temperature diagnostic.",
    "degasser_outlet_liquid_flow": "Duplicates Qp; the liquid-only model conserves inlet mass.",
    "injectionpump_outlet_temperature": "Isothermal pump model has no outlet-temperature output.",
    "hex_primary_outlet_pressure": "Hydraulic measurement represented by HEX_PDrop.",
    "hex_secondary_outlet_pressure": "No measured secondary pressure loss in this dataset.",
}


def _bind(bindings, target, column, unit):
    section, *parts = target.split(".")
    binding = Binding(column=column, unit=unit)
    if section == "inlets":
        set_nested(bindings.inlets, parts, binding)
    else:
        getattr(bindings, section)[parts[0]] = binding


def load_legacy_design(folder: str | Path) -> LegacyDesign:
    """Convert all project snapshots and report unknown fields without silently discarding them."""
    folder = Path(folder)
    data_files = [path for path in folder.glob("*.csv") if "trajectory" not in path.name]
    csv_path = data_files[0] if len(data_files) == 1 else None
    columns = set()
    if csv_path is not None:
        with csv_path.open() as handle:
            columns = set(next(csv.reader(handle, delimiter=";")))
    diagram = read_json(folder / "diagram.json")["cells"]
    raw = {p.stem: read_json(p) for p in sorted(folder.glob("*.param"))}
    ids = {value["id"]: key for key, value in raw.items()}
    nodes = {c["id"] for c in diagram if c["type"] == "devs.Model"}
    if nodes != ids.keys():
        raise ValueError("Diagram nodes and .param files must match exactly")
    edges = [c for c in diagram if c["type"] == "devs.Link"]
    incoming = {ids[c["target"]["id"]]: ids[c["source"]["id"]] for c in edges}
    outgoing = {ids[c["source"]["id"]]: ids[c["target"]["id"]] for c in edges}
    types = {n: TYPES.get(r["type"], r["type"]) for n, r in raw.items()}
    for name, kind in list(types.items()):
        if kind == "reservoir":
            types[name] = "injection_reservoir" if name in incoming else "production_reservoir"
    modules, bindings, ignored, unmapped = {}, {}, {}, []
    boundary = {"stream_defaults": {}, "fluids": {}, "inputs": {}, "streams": {}}

    def properties(name, index=0):
        return mapping.snapshot(raw[name]["parameters"]["property"], index)

    def neighbour_at(name, timestamp):
        times = raw[name]["parameters"]["timestamps"]
        eligible = [i for i, time in enumerate(times) if time <= timestamp]
        if not eligible:
            raise ValueError(f"{name}: no neighbour parameters valid at {timestamp}")
        return properties(name, eligible[-1])

    for name, item in raw.items():
        kind = types[name]
        known = PROPERTIES["reservoir" if "reservoir" in kind else kind]
        unmapped += [
            f"{name}.parameters.{key}" for key in item["parameters"]["property"] if key not in known
        ]
        snapshots = []
        for i, timestamp in enumerate(item["parameters"]["timestamps"]):
            props = properties(name, i)
            if "reservoir" in kind:
                well = outgoing[name] if kind == "production_reservoir" else incoming[name]
                params = mapping.reservoir_params_from_gemini(
                    props, neighbour_at(well, timestamp), kind.split("_")[0]
                )
            elif kind == "production_well":
                esp = outgoing.get(name)
                params = mapping.productionwell_params_from_gemini(
                    props,
                    base_path=folder,
                    esp_property=neighbour_at(esp, timestamp) if types.get(esp) == "esp" else None,
                )
            elif kind == "injection_well":
                params = mapping.injectionwell_params_from_gemini(props, base_path=folder)
            else:
                params = getattr(mapping, f"{kind}_params_from_gemini")(props)
            if kind == "injection_pump" and "InjectorPump_PowerDraw" in columns:
                # NOTE(refactor): example Q*deltaP/PowerDraw is 0.80000 (within rounding).
                # No curves exist, so use the pressure-setpoint variant with efficiency 0.8;
                # the standalone equipment default stays 0.7.
                params["efficiency"] = 0.8
            # Geometry models become plain JSON values at the portable config boundary.
            from gemini.core.modules.catalogue import get

            params = get(kind)(**params).state_dict()[""]["params"]
            snapshots.append(DatedParams(valid_from=timestamp, params=params))
        modules[name] = ModuleDesign(type=kind, params=snapshots)
        bound = ModuleBindings()
        for section, tags in item["tagnames"].items():
            if section == "timestamps":
                continue
            for tag, values in tags.items():
                key = f"{name}.tagnames.{section}.{tag}"
                if not any(values):
                    ignored[key] = "Empty tag: no data column is bound."
                elif section != "measured":
                    ignored[key] = "Legacy write destination; Results owns output storage."
                elif len(set(values)) > 1:
                    unmapped.append(key + " (time-varying sensor columns are unsupported)")
                elif tag in TAGS.get(kind, {}):
                    target, unit = TAGS[kind][tag]
                    _bind(bound, target, values[0], unit)
                elif kind == "production_well" and tag in {
                    "productionwell_flow",
                    "productionwell_wellhead_pressure",
                    "productionwell_wellhead_temperature",
                }:
                    ignored[key] = (
                        "No measured sandface boundary: this well is evaluated in the "
                        "chained scenario only."
                    )
                elif tag in IGNORED_TAGS:
                    ignored[key] = IGNORED_TAGS[tag]
                else:
                    unmapped.append(key)
        # NOTE(refactor): project tags omit these CSV channels and secondary absolute pressure.
        # Supplements are explicit, dataset-specific, and applied only when the columns exist.
        supplements = []
        if kind == "filter" and "p" in bound.inlets.get("inlet", {}):
            column = bound.inlets["inlet"]["p"].column.replace("_Pin", "_PDrop")
            supplements.append(("measured.pressure_drop", column, "bar"))
        elif kind == "degasser":
            supplements.append(("inlets.inlet.T", "T_p_in", "degC"))
            ignored[f"{name}.parameters.heat_transfer_coeff"] = (
                "Preserved as metadata; liquid-only passthrough has no gas/thermal model."
            )
        elif kind == "heat_exchanger":
            supplements.extend(
                [
                    ("measured.duty", "Thermal_PowerGen", "W"),
                    ("measured.dp_hot", "HEX_PDrop", "bar"),
                ]
            )
            if columns:
                boundary["stream_defaults"][name] = {"cold_in": {"p": 5e5}}
        elif kind == "production_reservoir":
            supplements.append(("controls.m_dot", "Qp", "m3/h"))
        for target, column, unit in supplements:
            if column in columns:
                _bind(bound, target, column, unit)
        if bound.controls or bound.inlets:
            bindings[name] = bound
        if kind == "injection_pump":
            # NOTE(refactor): no injection curves are supplied; use measured discharge setpoint.
            # The example efficiency is explicit in the snapshot; no curve is fabricated.
            boundary["inputs"][name] = {"pressure_setpoint": 5.15e6}
    # NOTE(refactor): expand the buried pump into two physical well segments. The riser
    # is an explicit handwritten child, preserving the previous physical segmentation.
    for name, item in list(modules.items()):
        esp = outgoing.get(name)
        if item.type != "production_well" or types.get(esp) != "esp":
            continue
        riser = name + "_riser"
        if riser in modules:
            raise ValueError(f"Generated riser name conflicts with {riser}")
        above = item.model_copy(deep=True)
        for snapshot in item.params:
            snapshot.params["segment"] = "below_esp"
        for snapshot in above.params:
            snapshot.params["segment"] = "above_esp"
        modules[riser] = above
        boundary.setdefault("well_risers", {})[name] = riser
    reservoir_name = next(n for n, m in modules.items() if m.type == "production_reservoir")
    p = modules[reservoir_name].params[-1].params
    raw_fluid = properties(reservoir_name, -1)
    brine = Fluid(
        liquid_density=p.get("liquid_density") or 1000,
        liquid_viscosity=p.get("liquid_viscosity") or 0.001,
        salinity=raw_fluid.get("salinity", 0),
        co2_mass_fraction=raw_fluid.get("co2_mass_fraction", 0),
        gas_mass_fraction=raw_fluid.get("gas_mass_fraction", 0),
    )
    if {"Thermal_PowerGen", "Qp", "T_p_in", "T_p_out"} <= columns:
        # NOTE(refactor): retain the earlier measured bulk heat-capacity assumption.
        brine = Fluid.model_validate(
            brine.model_dump() | {"specific_heat": 4.410e6 / brine.liquid_density}
        )
        boundary["assumptions"] = [
            "Example bulk heat capacity 4.410 MJ/m3/K inferred from its heat balance.",
            "Unmeasured secondary inlet pressure assumed 5 bar absolute.",
            "Injection-pump scenario setpoint 51.5 bar; twin uses measured setpoint.",
        ]
    for item in modules.values():
        item.fluid = brine
    boundary.pop("fluids", None)
    node_map = NODE_PATHS | {"production_well_c774_riser": "doublet.riser"}
    if set(modules) != set(node_map):
        raise ValueError("Project nodes do not match the legacy bridge node table")
    modules = {node_map[k]: v for k, v in modules.items()}
    bindings = {node_map[k]: v for k, v in bindings.items()}
    for key in ("stream_defaults", "inputs"):
        boundary[key] = {node_map[k]: v for k, v in boundary[key].items()}
    boundary.pop("well_risers", None)
    bindings[""] = ModuleBindings(
        inlets={
            "secondary": {
                "m_dot": Binding(column="Qs", unit="m3/h"),
                "T": Binding(column="T_s_in", unit="degC"),
            }
        },
    )
    # NOTE(refactor): two-control simulations need an assumed secondary boundary.
    # Store 40 kg/s, 20 C and 5 bar explicitly; measured replay never uses these defaults.
    boundary["root_inputs"] = {
        "secondary": {"m_dot": 40, "T": 293.15, "p": 5e5, "fluid": brine.model_dump(mode="json")},
    }
    boundary.setdefault("assumptions", []).append(
        "Profiles lacking secondary measurements assume 40 kg/s at 20 C and 5 bar."
    )
    conf = read_json(folder / "plant.conf")
    for key in unmapped:
        warnings.warn(f"Unmapped GEMINI field: {key}", stacklevel=2)
    return LegacyDesign(
        name=folder.name,
        modules=modules,
        bindings=bindings,
        boundary=boundary,
        timestep=conf["database"]["calculated"]["interval"],
        ignored=ignored,
        unmapped=unmapped,
    )
