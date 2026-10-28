"""Import GEMINI projects with explicit parameter, port and sensor-tag accounting."""

import csv
import json
import warnings
from pathlib import Path

from gemini.core.config import param_mapping as mapping
from gemini.core.config.schema import (
    Binding,
    DatedParams,
    Link,
    ModuleBindings,
    ModuleConfig,
    PlantConfig,
)

GEMINI_PORTS = {
    "production_reservoir": {"out": "sandface"},
    "injection_reservoir": {"in": "sandface"},
    "productionwell": {"in": "bottom", "out": "wellhead"},
    "injectionwell": {"in": "wellhead", "out": "bottom"},
    "esp": {"in": "suction", "out": "discharge"},
    "injectionpump": {"in": "suction", "out": "discharge"},
    "filter": {"in": "inlet", "out": "outlet"},
    "degasser": {"in": "inlet", "out1": "liquid", "out2": "gas"},
    "heatexchanger": {
        "PrimIn": "hot_in",
        "PrimOut": "hot_out",
        "SecIn": "cold_in",
        "SecOut": "cold_out",
    },
}
TYPES = {
    "production_well": "productionwell",
    "injection_well": "injectionwell",
    "heat_exchanger": "heatexchanger",
    "injection_pump": "injectionpump",
}
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
            " wellbore_radius productivity_index injectivity_index"
        ).split()
    ),
    "heatexchanger": set(
        (
            "heat_transfer_coeff ua arrangement dp_hot_nominal dp_cold_nominal "
            "m_dot_hot_nominal m_dot_cold_nominal"
        ).split()
    ),
    "degasser": {"heat_transfer_coeff"},
    "filter": {"clogging_dp"},
    "injectionpump": {"injectionpump_no_stage", "injectionpump_type"},
}
for _prefix in ("productionwell", "injectionwell"):
    PROPERTIES[_prefix] = {
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
    PROPERTIES[_prefix].add("wellbore_radius")

# Each target is inputs.field, streams.port.field, or measured.output.
TAGS = {
    "esp": {
        "esp_frequency": ("inputs.frequency", "Hz"),
        "esp_flow": ("streams.suction.m_dot", "m3/h"),
        "esp_inlet_pressure": ("streams.suction.p", "bar"),
        "esp_inlet_temperature": ("streams.suction.T", "degC"),
        "esp_head": ("measured.head", "bar"),
        "esp_outlet_pressure": ("measured.discharge_pressure", "bar"),
        "esp_power_consumption": ("measured.power", "W"),
    },
    "filter": {
        "filter_flow": ("streams.inlet.m_dot", "m3/h"),
        "filter_inlet_pressure": ("streams.inlet.p", "bar"),
        "filter_inlet_temperature": ("streams.inlet.T", "degC"),
    },
    "degasser": {
        "degasser_inlet_flow": ("streams.inlet.m_dot", "m3/h"),
        "degasser_pressure": ("streams.inlet.p", "bar"),
    },
    "injectionpump": {
        "injectionpump_flow": ("streams.suction.m_dot", "m3/h"),
        "injectionpump_inlet_pressure": ("streams.suction.p", "bar"),
        "injectionpump_inlet_temperature": ("streams.suction.T", "degC"),
        "injectionpump_outlet_pressure": ("inputs.discharge_pressure", "bar"),
        "injectionpump_power_consumption": ("measured.power", "W"),
        "injectionpump_frequency": ("inputs.frequency", "Hz"),
        "injectionpump_head": ("measured.head", "bar"),
    },
    "injectionwell": {
        "injectionwell_flow": ("streams.wellhead.m_dot", "m3/h"),
        "injectionwell_wellhead_pressure": ("streams.wellhead.p", "bar"),
        "injectionwell_wellhead_temperature": ("streams.wellhead.T", "degC"),
        "injectionwell_bottomhole_pressure": ("measured.bottomhole_pressure", "bar"),
        "injectionwell_bottomhole_temperature": ("measured.bottomhole_temperature", "degC"),
    },
    "heatexchanger": {
        "hex_primary_flow": ("streams.hot_in.m_dot", "m3/h"),
        "hex_primary_inlet_pressure": ("streams.hot_in.p", "bar"),
        "hex_primary_inlet_temperature": ("streams.hot_in.T", "degC"),
        "hex_primary_outlet_temperature": ("measured.hot_out_T", "degC"),
        "hex_secondary_flow": ("streams.cold_in.m_dot", "m3/h"),
        "hex_secondary_inlet_pressure": ("streams.cold_in.p", "bar"),
        "hex_secondary_inlet_temperature": ("streams.cold_in.T", "degC"),
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
    if section == "streams":
        bindings.streams.setdefault(parts[0], {})[parts[1]] = binding
    else:
        getattr(bindings, section)[parts[0]] = binding


def load_gemini(folder: str | Path) -> PlantConfig:
    """Convert all project snapshots and report unknown fields without silently discarding them."""
    folder = Path(folder)
    csv_path = folder / "geothermal_example_dataset.csv"
    columns = set()
    if csv_path.exists():
        with csv_path.open() as handle:
            columns = set(next(csv.reader(handle, delimiter=";")))
    diagram = json.loads((folder / "diagram.json").read_text())["cells"]
    raw = {p.stem: json.loads(p.read_text()) for p in sorted(folder.glob("*.param"))}
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
            elif kind == "productionwell":
                esp = outgoing.get(name)
                params = mapping.productionwell_params_from_gemini(
                    props,
                    base_path=folder,
                    esp_property=neighbour_at(esp, timestamp) if types.get(esp) == "esp" else None,
                )
            elif kind == "injectionwell":
                params = mapping.injectionwell_params_from_gemini(props, base_path=folder)
            else:
                params = getattr(mapping, f"{kind}_params_from_gemini")(props)
            if kind == "injectionpump" and "InjectorPump_PowerDraw" in columns:
                # NOTE(refactor): example Q*deltaP/PowerDraw is 0.80000 (within rounding).
                # No curves exist, so use the pressure-setpoint variant with efficiency 0.8;
                # the standalone equipment default stays 0.7.
                params["efficiency"] = 0.8
            # Geometry models become plain JSON values at the portable config boundary.
            from gemini.core.engine.registry import get

            params = get(kind).Params.model_validate(params).model_dump(mode="json")
            snapshots.append(DatedParams(valid_from=timestamp, params=params))
        modules[name] = ModuleConfig(type=kind, params=snapshots)
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
                elif kind == "productionwell" and tag in {
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
        if kind == "filter" and "p" in bound.streams.get("inlet", {}):
            column = bound.streams["inlet"]["p"].column.replace("_Pin", "_PDrop")
            supplements.append(("measured.pressure_drop", column, "bar"))
        elif kind == "degasser":
            supplements.append(("streams.inlet.T", "T_p_in", "degC"))
            ignored[f"{name}.parameters.heat_transfer_coeff"] = (
                "Preserved as metadata; liquid-only passthrough has no gas/thermal model."
            )
        elif kind == "heatexchanger":
            supplements.extend(
                [
                    ("measured.duty", "Thermal_PowerGen", "W"),
                    ("measured.dp_hot", "HEX_PDrop", "bar"),
                ]
            )
            if columns:
                boundary["stream_defaults"][name] = {"cold_in": {"p": 5e5}}
        elif kind == "production_reservoir":
            supplements.append(("inputs.m_dot", "Qp", "m3/h"))
        for target, column, unit in supplements:
            if column in columns:
                _bind(bound, target, column, unit)
        if bound.inputs or bound.streams:
            bindings[name] = bound
        if kind == "injectionpump":
            # NOTE(refactor): no injection curves are supplied; use measured discharge setpoint.
            # The example efficiency is explicit in the snapshot; no curve is fabricated.
            boundary["inputs"][name] = {"discharge_pressure": 5.15e6}
    links = []
    for edge in edges:
        source, target = ids[edge["source"]["id"]], ids[edge["target"]["id"]]
        try:
            links.append(
                Link(
                    source=source,
                    source_port=GEMINI_PORTS[types[source]][edge["source"]["port"]],
                    target=target,
                    target_port=GEMINI_PORTS[types[target]][edge["target"]["port"]],
                )
            )
        except KeyError as exc:
            raise ValueError(f"Unknown GEMINI port on {source} -> {target}: {exc}") from exc
    # NOTE(refactor): expand the buried pump into two physical well segments. The riser
    # is a separate graph child so every link still carries an ordinary Stream.
    for name, item in list(modules.items()):
        esp = outgoing.get(name)
        if item.type != "productionwell" or types.get(esp) != "esp":
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
        for link in links:
            if link.source == esp:
                link.source, link.source_port = riser, "wellhead"
        links.append(Link(source=esp, source_port="discharge", target=riser, target_port="bottom"))
        boundary.setdefault("well_risers", {})[name] = riser
    # Consistent fluid identity is needed by Stream.volumetric_flow and hydraulic calculations.
    reservoir = next((m for m in modules.values() if m.type == "production_reservoir"), None)
    if reservoir:
        p = reservoir.params[-1].params
        fluid_name = folder.name + "_brine"
        boundary["fluids"][fluid_name] = {
            "RHOL": p.get("liquid_density") or 1000,
            "VISL": p.get("liquid_viscosity") or 0.001,
        }
        if {"Thermal_PowerGen", "Qp", "T_p_in", "T_p_out"} <= columns:
            # NOTE(refactor): example duty/(Q * deltaT) implies 4.410 MJ/m3/K.
            # Use that explicit bulk heat capacity with the supplied 1068 kg/m3 density;
            # this assumption is dataset-specific and does not alter default/golden fluids.
            boundary["fluids"][fluid_name]["CPL"] = 4.410e6 / boundary["fluids"][fluid_name]["RHOL"]
            boundary["assumptions"] = [
                "Example bulk heat capacity 4.410 MJ/m3/K inferred from its heat balance.",
                "Unmeasured secondary inlet pressure assumed 5 bar absolute.",
                (
                    "Injection-pump default scenario setpoint 51.5 bar; twin uses the "
                    "measured setpoint."
                ),
            ]
        for module in modules.values():
            module.fluid = fluid_name
    conf = json.loads((folder / "plant.conf").read_text())
    for key in unmapped:
        warnings.warn(f"Unmapped GEMINI field: {key}", stacklevel=2)
    return PlantConfig(
        name=folder.name,
        modules=modules,
        links=links,
        bindings=bindings,
        boundary=boundary,
        timestep=conf["database"]["calculated"]["interval"],
        ignored=ignored,
        unmapped=unmapped,
    )
