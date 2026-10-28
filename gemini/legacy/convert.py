"""Conversion between old GEMINI files and the new plant, Dataset and Results objects."""

from copy import deepcopy

import pandas as pd

from gemini.core.data.dataset import Dataset
from gemini.core.modules import catalogue
from gemini.core.modules.plants.doublet import Doublet
from gemini.core.modules.wiring import trace_wiring
from gemini.core.physics import units
from gemini.core.types import Binding, ModuleBindings
from gemini.legacy._loader import load_legacy_design
from gemini.legacy.tables import NODE_PATHS, PORTS, TYPES

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
    "m_dot": "production_rate",
    "esp_frequency": "esp_frequency",
    "injection_pressure": "injection_pressure",
    "secondary.m_dot": "secondary_rate",
    "secondary.T": "secondary_temperature",
}


def _require_folder(project):
    if project._folder is None:
        raise ValueError("Legacy conversion requires a GeminiProject returned by read_project")
    return project._folder


def _new_name(path, section, field, port=None):
    if path == "" and section == "inputs":
        return _ROOT_COLUMNS.get(field, field)
    prefix = f"{path}." if path else ""
    if section == "streams":
        return f"{prefix}{port}.{field}"
    return f"{prefix}{field}"


def _converted_bindings(design):
    converted, sources = {}, {}
    for path, old in design.bindings.items():
        bound = ModuleBindings()
        for field, binding in old.inputs.items():
            name = _new_name(path, "inputs", field)
            bound.inputs[field] = Binding(column=name, unit=_SI_UNITS[binding.unit])
            sources[name] = binding
        for port, fields in old.streams.items():
            bound.streams[port] = {}
            for field, binding in fields.items():
                name = _new_name(path, "streams", field, port)
                bound.streams[port][field] = Binding(column=name, unit=_SI_UNITS[binding.unit])
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
    leaves = {
        path: catalogue.create(item.type, item.at().params, fluid=item.fluid)
        for path, item in design.modules.items()
    }
    doublet_names = {"reservoir", "well", "esp", "riser", "injector", "sink"}
    doublet = Doublet(**{name: leaves[f"doublet.{name}"] for name in doublet_names})
    for name in list(plant._children):
        delattr(plant, name)
    plant.doublet = doublet
    for name in ("degasser", "filter_hot", "heat_exchanger", "filter_return", "injection_pump"):
        setattr(plant, name, leaves[name])
    for path, item in design.modules.items():
        module = plant.get_submodule(path)
        module.param_history = [snapshot.model_copy(deep=True) for snapshot in item.params]
        module.params = module.params_at(None)
        module._active_from = item.at().valid_from
        module._active_params = item.at().params.copy()
        module._param_overrides = {}
    plant.bindings, _ = _converted_bindings(design)
    plant.boundary = deepcopy(design.boundary)
    plant._fluid = next(iter(design.modules.values())).fluid
    plant.fluid = plant._resolve_fluid()
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
    """Return an old-project copy suitable for writing through the faithful raw writer.

    The bridge preserves every original raw property. Current parameter conversion is
    deliberately limited to values originating from that template; unsupported new fields
    remain represented only in the new plant JSON.
    """
    if nodes is not None and nodes != plant.legacy_info.get("nodes", nodes):
        raise ValueError("The supplied node map differs from the plant's legacy conversion map")
    return template.model_copy(deep=True)


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
            plant.last_result.inputs.model_dump()
            if getattr(plant, "last_result", None) is not None
            else deepcopy(plant.boundary["root_inputs"])
        )
        inputs.setdefault("m_dot", 40.0)
        inputs.setdefault("esp_frequency", 60.0)
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
