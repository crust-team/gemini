"""Conversion between old GEMINI files and the new plant, Dataset and Results objects."""

from copy import deepcopy

import pandas as pd

from gemini.core.data.dataset import Dataset
from gemini.core.modules.wiring import trace_wiring
from gemini.core.physics import units
from gemini.core.types import Binding, ModuleBindings
from gemini.utils.strings import join_path

from ._loader import load_legacy_design
from .tables import NODE_PATHS, PORTS, TYPES

_SI_UNITS = {
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
_ROOT_COLUMNS = {
    "secondary.m_dot": "secondary_rate",
    "secondary.T": "secondary_temperature",
}


def _require_folder(project):
    if project._folder is None:
        raise ValueError("Legacy conversion requires a GeminiProject returned by read_project")
    return project._folder


def _new_name(path, section, field, port=None):
    if path == "" and section == "controls":
        return _ROOT_COLUMNS.get(field, field)
    if section == "inlets":
        return join_path(path, f"{port}.{field}")
    return join_path(path, field)


def _converted_bindings(design):
    converted, sources = {}, {}
    for path, old in design.bindings.items():
        bound = ModuleBindings()
        for field, binding in old.controls.items():
            name = _new_name(path, "controls", field)
            bound.controls[field] = Binding(column=name, unit=_SI_UNITS[binding.unit])
            sources[name] = binding
        for field, binding in old.boundaries.items():
            name = _new_name(path, "boundaries", field)
            bound.boundaries[field] = Binding(column=name, unit=_SI_UNITS[binding.unit])
            sources[name] = binding
        for port, fields in old.inlets.items():
            bound.inlets[port] = {}
            for field, binding in fields.items():
                name = _new_name(path, "inlets", field, port)
                bound.inlets[port][field] = Binding(column=name, unit=_SI_UNITS[binding.unit])
                sources[name] = binding
        for field, binding in old.measured.items():
            name = _new_name(path, "measured", field)
            bound.measured[field] = Binding(column=name, unit=_SI_UNITS[binding.unit])
            sources[name] = binding
        for field, binding in old.state.items():
            name = _new_name(path, "state", field)
            bound.state[field] = Binding(column=name, unit=_SI_UNITS[binding.unit])
            sources[name] = binding
        converted[path] = bound
    return converted, sources


def to_plant(project, plant, nodes=None):
    """Fill an existing example plant with converted SI parameters, histories and bindings."""
    design = load_legacy_design(_require_folder(project))
    if nodes is not None:
        expected = {node_id: NODE_PATHS[node.name] for node_id, node in project.nodes.items()}
        if nodes != expected:
            raise ValueError(
                f"Explicit legacy node map differs: {set(nodes.items()) ^ set(expected.items())}"
            )
    for path, item in design.modules.items():
        module = plant.get_submodule(path)
        if module.name != item.type:
            raise ValueError(f"{path}: expected {module.name!r}, legacy maps to {item.type!r}")
        module.param_history = [snapshot.model_copy(deep=True) for snapshot in item.params]
        for name, value in module.params_at(None).items():
            module.get_parameter(name).set(value, explicit=False)
        module._active_from = item.at().valid_from
        module._param_overrides = {}
        module.fluid = item.fluid
    plant.bindings, _ = _converted_bindings(design)
    plant.boundary = deepcopy(design.boundary)
    plant.fluid = next(iter(design.modules.values())).fluid
    plant.legacy_info = {
        "ignored": design.ignored,
        "unmapped": design.unmapped,
        "nodes": nodes
        or {node_id: NODE_PATHS[node.name] for node_id, node in project.nodes.items()},
    }
    return plant


def to_dataset(project, frame_old):
    """Rename old tag columns, convert numeric values to SI and return an in-memory Dataset."""
    design = load_legacy_design(_require_folder(project))
    bindings, sources = _converted_bindings(design)
    del bindings
    frame = frame_old.copy()
    time_column = next(
        (name for name in frame.columns if pd.api.types.is_datetime64_any_dtype(frame[name])),
        frame.columns[0],
    )
    index = pd.to_datetime(frame.pop(time_column), utc=True)
    converted = {}
    metadata = {}
    missing = []
    for name, source in sources.items():
        if source.column not in frame:
            missing.append(source.column)
            continue
        converted[name] = (
            frame[source.column].map(lambda value: units.to_si(value, source.unit)).to_numpy()
        )
        metadata[name] = _SI_UNITS[source.unit]
    if missing:
        raise ValueError("Old CSV is missing bound tag columns: " + ", ".join(sorted(set(missing))))
    for name in frame.filter(like="status").columns:
        converted[name] = frame[name].to_numpy()
    if "Pwh_prod" in frame:
        converted["production_wellhead_pressure"] = (
            frame["Pwh_prod"].map(lambda value: units.to_si(value, "bar")).to_numpy()
        )
        metadata["production_wellhead_pressure"] = "Pa"
    return Dataset.from_frame(pd.DataFrame(converted, index=index), units=metadata)


def from_plant(plant, template, nodes=None):
    """Convert current parameters and dated histories into an old-project copy.

    Properties without a faithful inverse (notably trajectory tables) retain the template's
    raw value. New-format-only fields remain in the plant JSON and are not invented in GEMINI.
    """
    node_map = nodes or getattr(plant, "legacy_info", {}).get("nodes")
    if node_map is None:
        raise ValueError("from_plant requires nodes or a plant created by legacy.to_plant")
    unknown = sorted(set(template.nodes) - set(node_map))
    if unknown:
        raise ValueError(f"Legacy node map is missing node ids: {unknown}")
    converted = template.model_copy(deep=True)
    for node_id, properties in converted.params.items():
        path = node_map[node_id]
        owner = plant.get_submodule(path)
        dates = [snapshot.valid_from for snapshot in owner.param_history]
        for name, legacy_param in properties.items():
            source = owner
            if name == "productionwell_productivity_index":
                source = plant.get_submodule("doublet.reservoir")
            elif name == "injectionwell_injectivity_index":
                source = plant.get_submodule("doublet.sink")
            elif name == "wellbore_radius" and path.endswith(".well"):
                source = plant.get_submodule("doublet.reservoir")
            elif name == "wellbore_radius" and path.endswith(".injector"):
                source = plant.get_submodule("doublet.sink")
            export_dates = dates or legacy_param.timestamps
            if len(export_dates) == len(legacy_param.timestamps) and all(
                _same_time(new, old) for new, old in zip(export_dates, legacy_param.timestamps)
            ):
                export_dates = legacy_param.timestamps
            values = []
            for index, timestamp in enumerate(export_dates):
                params = source.params_at(timestamp)
                original = legacy_param.values[min(index, len(legacy_param.values) - 1)]
                values.append(_legacy_property(name, params, original))
            legacy_param.timestamps = list(export_dates)
            legacy_param.values = values
    return converted


def _same_time(left, right):
    if left is None or right is None:
        return left is right
    return pd.Timestamp(left).tz_localize(None) == pd.Timestamp(right).tz_localize(None)


def _coefficients(value):
    return list(map(float, value.split(";"))) if isinstance(value, str) else list(value)


def _coefficient_value(values, original):
    values = list(values)
    if _coefficients(original) == values:
        return original
    if isinstance(original, str):
        return ";".join(format(value, ".17g") for value in values)
    return values


def _legacy_property(name, params, original):
    """Return one old-format property while preserving unchanged raw representations."""
    direct = {
        "esp_depth": "setting_depth",
        "esp_no_stage": "no_stages",
        "esp_tubing": "tubing",
        "esp_type": "pump_type",
        "heat_transfer_coeff": ("ua" if "ua" in params else "heat_transfer_coeff"),
        "injectionpump_no_stage": "no_stages",
        "injectionpump_type": "pump_type",
        "reservoir_thickness": "thickness",
        "reservoir_radius": "drainage_radius",
        "reservoir_top": "top_depth",
        "liquid_density": "liquid_density",
        "liquid_viscosity": "liquid_viscosity",
        "skin": "skin",
        "wellbore_radius": "wellbore_radius",
    }
    if name in direct:
        value = params[direct[name]]
    elif name == "esp_head_coeff":
        return _coefficient_value(params["head_coeff"], original)
    elif name == "esp_power_coeff":
        return _coefficient_value(params["power_coeff"], original)
    elif name == "esp_correction_factor":
        return _coefficient_value(
            [params["correction_factor"][0], units.pa_to_bar(params["correction_factor"][1])],
            original,
        )
    elif name in {"esp_bep_flow", "esp_min_flow", "esp_max_flow"}:
        value = units.m3s_to_m3h(params[name.removeprefix("esp_")])
    elif name == "reservoir_pressure":
        value = units.pa_to_bar(params["pressure"])
    elif name == "reservoir_temperature":
        value = units.k_to_c(params["temperature"])
    elif name == "reservoir_permeability":
        value = units.m2_to_md(params["permeability"])
    elif name.endswith("_soil_temperature"):
        value = units.k_to_c(params["soil_temperature"])
    elif name.endswith("_friction_correlation"):
        value = params["friction_correlation"]
    elif name.endswith("_friction_correlation_2p"):
        value = params["friction_correlation_2p"]
    elif name.endswith("_friction_correction_factors"):
        value = list(params["correction_factors"])
    elif name.endswith("_productivity_index"):
        value = units.index_from_si(params["productivity_index"])
    elif name.endswith("_injectivity_index"):
        value = units.index_from_si(params["injectivity_index"])
    else:
        return original
    return original if value == original else value


def _from_si(value, unit):
    if unit in ("Pa", "K", "m3/s", "kg/s", "Hz", "W", "-"):
        return value
    if unit == "bar":
        return value / 1e5
    if unit == "degC":
        return value - 273.15
    if unit == "m3/h":
        return value * 3600
    return value


def results_to_frame(results, project, nodes=None):
    """Convert predicted bound outputs to their old tag columns and units."""
    del nodes
    design = load_legacy_design(_require_folder(project))
    frame = results.to_frame()
    output = pd.DataFrame({"Timestamp": frame.index.tz_convert("UTC").tz_localize(None)})
    for path, bound in design.bindings.items():
        if path not in frame.columns.get_level_values(0):
            continue
        for field, binding in bound.measured.items():
            if (path, field) in frame:
                output[binding.column] = (
                    frame[path, field].map(lambda value: _from_si(value, binding.unit)).to_numpy()
                )
    return output


def check_wiring(plant, project, nodes=None):
    """Return an empty list when observed plant stream identities match the old diagram."""
    node_map = nodes or {node_id: NODE_PATHS[node.name] for node_id, node in project.nodes.items()}
    try:
        inputs = (
            dict(plant.last_result.inlets)
            if getattr(plant, "last_result", None) is not None
            else deepcopy(plant.boundary["root_inputs"])
        )
        if getattr(plant, "last_result", None) is None:
            plant.set_inputs(
                {
                    "doublet.reservoir.m_dot": 40.0,
                    "doublet.esp.frequency": 60.0,
                    "injection_pump.pressure_setpoint": 5.15e6,
                }
            )
        traced = trace_wiring(plant, inputs)
    except Exception as exc:
        return [f"Could not trace plant wiring: {exc}"]
    incoming = {link.target for link in project.links}
    expected, errors = set(), []
    for link in project.links:
        try:
            source_node, target_node = project.nodes[link.source], project.nodes[link.target]
            source_type = TYPES.get(source_node.type, source_node.type)
            target_type = TYPES.get(target_node.type, target_node.type)
            if source_type == "reservoir":
                source_type = (
                    "injection_reservoir" if source_node.id in incoming else "production_reservoir"
                )
            if target_type == "reservoir":
                target_type = (
                    "injection_reservoir" if target_node.id in incoming else "production_reservoir"
                )
            source = (node_map[source_node.id], PORTS[source_type][link.source_port])
            target = (node_map[target_node.id], PORTS[target_type][link.target_port])
            if source == ("doublet.esp", "discharge"):
                expected.add((*source, "doublet.riser", "bottom"))
                source = ("doublet.riser", "wellhead")
            expected.add((*source, *target))
        except KeyError as exc:
            errors.append(f"Unmapped legacy diagram endpoint: {exc}")
    errors.extend(f"Missing connection: {edge}" for edge in sorted(expected - traced))
    errors.extend(f"Unexpected connection: {edge}" for edge in sorted(traced - expected))
    return errors
