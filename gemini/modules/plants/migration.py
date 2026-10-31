"""Convert a format 1 plant file (class paths, one entry per module) to a format 2 spec."""

from copy import deepcopy

from gemini.backends import runtime
from gemini.errors import GeminiError, ValidationError
from gemini.modules._utils import design
from gemini.modules._utils.serialization import FORMAT, SECTIONS, plain_value
from gemini.modules.plants import library, reader
from gemini.modules.plants.builder import Plant
from gemini.types.bindings import ModuleBindings
from gemini.types.fluid import Fluid
from gemini.utils.strings import join_path

RENAMED_NAMES = {
    "approach_T": "approach_temperature",
    "bep_flow": "best_efficiency_flow",
    "bep_ratio": "best_efficiency_ratio",
    "building_return_T": "building_return_temperature",
    "building_supply_T": "building_supply_temperature",
    "capped": "is_capped",
    "carnot_efficiency": "carnot_fraction",
    "clogging_dp": "clogging_pressure_drop",
    "correction_factor": "correction_factors",
    "depth": "borehole_depth",
    "dp": "nominal_pressure_drop",
    "dp_cold": "cold_pressure_drop",
    "dp_cold_nominal": "cold_nominal_pressure_drop",
    "dp_friction": "friction_pressure_drop",
    "dp_gravity": "gravity_pressure_drop",
    "dp_hot": "hot_pressure_drop",
    "dp_hot_nominal": "hot_nominal_pressure_drop",
    "dp_nominal": "nominal_pressure_drop",
    "flow_dp": "flow_pressure_drop",
    "fluid_mean_T": "fluid_mean_temperature",
    "fraction_of_carnot": "carnot_fraction",
    "friction_correlation_2p": "two_phase_friction_correlation",
    "ground_T": "ground_temperature",
    "head_coeff": "head_coefficients",
    "heat_loss_coefficient": "heat_loss_conductance",
    "heat_transfer_coeff": "heat_transfer_coefficient",
    "hydrostatic_dp": "hydrostatic_pressure_drop",
    "ice_heat_capacity": "ice_specific_heat",
    "in_operating_window": "is_in_operating_window",
    "lmtd": "log_mean_temperature_difference",
    "lorenz_efficiency": "lorenz_fraction",
    "m_dot_cold_nominal": "cold_nominal_mass_flow",
    "m_dot_hot_nominal": "hot_nominal_mass_flow",
    "m_dot_nominal": "nominal_mass_flow",
    "max_flow": "maximum_flow",
    "min_flow": "minimum_flow",
    "no_stages": "stage_count",
    "ntu": "transfer_units",
    "output_max": "maximum_output",
    "output_min": "minimum_output",
    "p_out": "outlet_pressure",
    "power_coeff": "power_coefficients",
    "production_T": "production_out_T",
    "rock_conductivity": "ground_conductivity",
    "rock_diffusivity": "ground_diffusivity",
    "skin_dp": "skin_pressure_drop",
    "thickness": "aquifer_thickness",
    "u_value": "heat_transfer_coefficient",
    "ua": "thermal_conductance",
    "water_heat_capacity": "water_specific_heat",
}
"""Parameter and output names of the first frozen API and their current names."""


FLUID_NAMES = {"liquid_density": "density", "liquid_viscosity": "viscosity"}
"""Fluid fields renamed in 0.2.0; a reservoir parameter of these names moved onto its fluid."""


RENAMED_PORTS = {
    "inlet": "fluid_in",
    "suction": "fluid_in",
    "feed_in": "fluid_in",
    "brine_in": "fluid_in",
    "outlet": "fluid_out",
    "discharge": "fluid_out",
    "mixed_out": "fluid_out",
    "retained_out": "fluid_out",
    "brine_out": "fluid_out",
    "first_in": "branch1_in",
    "second_in": "branch2_in",
    "first_out": "branch1_out",
    "second_out": "branch2_out",
    "blowdown_out": "waste_out",
    "secondary_in": "return_in",
    "secondary_out": "supply_out",
    "network_in": "supply_in",
    "network_out": "return_out",
    "building_in": "return_in",
    "building_out": "supply_out",
    "liquid": "liquid_out",
    "gas": "gas_out",
}
"""Port names before the ``<role>_in`` and ``<role>_out`` rule and their current names."""

SUFFIXED_PORTS = {"wellhead", "bottom", "sandface"}
"""Old port names that were an inlet on one module and an outlet on another."""


def _current_port(port, side):
    """Return the current name of ``port``, an old or current inlet or outlet name."""
    if port in SUFFIXED_PORTS:
        return f"{port}_{'in' if side == 'inlets' else 'out'}"
    return RENAMED_PORTS.get(port, port)


def _current_end(end, side):
    """Return the ``"path.port"`` end of a connection with the current port name."""
    path, _, port = end.rpartition(".")
    return join_path(path, _current_port(port, side))


def _current_ends(ends, side):
    """Return one end of a plant port, or the list of ends several share, with current ports."""
    if isinstance(ends, list):
        return [_current_end(end, side) for end in ends]
    return _current_end(ends, side)


def _current_binding_names(bindings):
    """Return flat bindings of one module with the current port of each ``port.field`` key."""
    current = {}
    for key, value in bindings.items():
        port, dot, field = key.partition(".")
        current[f"{_current_port(port, 'inlets')}{dot}{field}"] = value
    return current


def _current_stored_inputs(boundary):
    """Return stored ``boundary`` values whose streams are keyed by current port names."""
    current = dict(boundary)
    if "root_inputs" in boundary:
        current["root_inputs"] = {
            _current_port(port, "inlets"): value for port, value in boundary["root_inputs"].items()
        }
    if "stream_defaults" in boundary:
        current["stream_defaults"] = {
            path: {_current_port(port, "inlets"): value for port, value in ports.items()}
            for path, ports in boundary["stream_defaults"].items()
        }
    return current


def _current_ports(spec):
    """Return a format 2 spec whose connection ends, plant ports and bindings use current ports."""
    for item in spec.get("connections", []):
        item["source"] = _current_end(item["source"], "outlets")
        item["target"] = _current_end(item["target"], "inlets")
    for side in ("inlets", "outlets"):
        if side in spec:
            spec[side] = {name: _current_ends(ends, side) for name, ends in spec[side].items()}
    spec["bindings"] = {
        path: _current_binding_names(values) for path, values in spec.get("bindings", {}).items()
    }
    if "boundary" in spec:
        spec["boundary"] = {
            path: _current_stored_inputs(values) for path, values in spec["boundary"].items()
        }
    return spec


def _failed(message, path=None):
    return ValidationError(message, code="migration_failed", path=path)


def _place(spec, path, params):
    """Put the params of the old module at ``path`` into the spec entry that holds it."""
    if not params:
        return
    parts = path.split(".")
    modules = spec["modules"]
    for index, part in enumerate(parts):
        if part not in modules:
            raise _failed(f"module {path!r} is not in the plant's wiring", path=path)
        entry = modules[part]
        if "modules" not in entry:
            prefix = ".".join(parts[index + 1 :])
            target = entry.setdefault("params", {})
            target.update({join_path(prefix, name): value for name, value in params.items()})
            return
        modules = entry["modules"]
    if params:
        raise _failed(f"module {path!r} is a group but has parameters", path=path)


def _flat_bindings(plant, path, nested):
    """Return the bindings of format 1, stored by section, in the flat form of format 2."""
    target = plant._find_submodule(path) if plant is not None else None
    return design.flat(target, ModuleBindings.model_validate(nested))


def _sections(entries, plant=None):
    default = runtime.get_default_fluid()
    sections = {"fluids": {}, "boundary": {}, "bindings": {}, "param_history": {}}
    for path, entry in entries.items():
        if "fluid" in entry and Fluid.model_validate(_fluid_names(entry["fluid"])) != default:
            sections["fluids"][path] = _fluid_names(entry["fluid"])
        if entry.get("boundary"):
            sections["boundary"][path] = deepcopy(entry["boundary"])
        for key, value in entry.get("bindings", {}).items():
            bound = join_path(path, key)
            sections["bindings"][bound] = _flat_bindings(plant, bound, value)
        history = entry.get("param_history", [])
        if len(history) != 1 or history[0].get("valid_from") is not None:
            sections["param_history"][path] = deepcopy(history)
    return {
        key: value
        for key, value in sections.items()
        if value or key in ("bindings", "param_history")
    }


def _changed(plant, path, params):
    """Return the stored params that differ from the starting value of the shipped plant."""
    module = plant._find_submodule(path)
    if module is None:
        raise _failed(f"module {path!r} is not in the plant's wiring", path=path)
    declarations = dict(module.named_parameters())
    return {
        name: value
        for name, value in params.items()
        if name not in declarations
        or not declarations[name].initialized
        or plain_value(declarations[name].value) != value
    }


def _structured(name, entries):
    spec = library.shipped(name)
    plant = library.build(name)
    for path, entry in entries.items():
        if path:
            _place(spec, path, _changed(plant, path, entry.get("params", {})))
    kept = {key: value for key, value in spec.items() if key not in SECTIONS}
    return kept | _sections(entries, plant)


def _handwritten(name, entries):
    params = {
        join_path(path, key): value
        for path, entry in entries.items()
        for key, value in entry.get("params", {}).items()
    }
    spec = {"format": FORMAT, "name": name, "type": name, "modules": {}, "connections": []}
    return spec | {"params": params} | _sections(entries)


def _current_names(values):
    """Return a mapping of parameters or bindings with the current name of each key."""
    return {RENAMED_NAMES.get(key, key): value for key, value in values.items()}


def _current_bindings(bindings):
    """Return the bindings of one module with the current name of each measured output."""
    inlets = {
        _current_port(port, "inlets"): value for port, value in bindings.get("inlets", {}).items()
    }
    return bindings | {"measured": _current_names(bindings.get("measured", {})), "inlets": inlets}


def _current_entry(entry):
    """Return one stored module entry with the current parameter and output names."""
    current = dict(entry)
    if "params" in entry:
        current["params"] = _current_names(entry["params"])
    if "param_overrides" in entry:
        current["param_overrides"] = [
            RENAMED_NAMES.get(name, name) for name in entry["param_overrides"]
        ]
    if "bindings" in entry:
        current["bindings"] = {
            path: _current_bindings(value) for path, value in entry["bindings"].items()
        }
    if "param_history" in entry:
        current["param_history"] = [
            item | {"params": _current_names(item["params"])} for item in entry["param_history"]
        ]
    return current


def _convert(old):
    if not isinstance(old, dict) or old.get("version") != 1:
        raise _failed(
            f"version = {old.get('version') if isinstance(old, dict) else old!r}; expected 1"
        )
    name = old["plant_type"].split(":")[-1].split(".")[-1]
    entries = {path: _current_entry(entry) for path, entry in old["modules"].items()}
    if library.has(name):
        spec = _current_fluids(_current_ports(_structured(name, entries)))
        problems = reader.problems(Plant, spec)
        if problems:
            raise _failed(
                f"{problems[0]['path']}: {problems[0]['message']}", path=problems[0]["path"]
            )
        return spec
    return _current_fluids(_handwritten(name, entries))


def _fluid_names(stored):
    """Return stored data with every fluid in it, at any depth, in the form of 0.2.0."""
    if isinstance(stored, list):
        return [_fluid_names(item) for item in stored]
    if not isinstance(stored, dict):
        return stored
    renamed = {FLUID_NAMES.get(key, key): _fluid_names(value) for key, value in stored.items()}
    if "property_model" in renamed:
        return Fluid.model_validate(renamed).model_dump(mode="json")
    return renamed


def _moved_fluid_params(spec, path, params):
    """Move the reservoir fluid parameters of ``params`` onto the fluids of their modules."""
    for name in [name for name in params if name.rsplit(".", 1)[-1] in FLUID_NAMES]:
        value = params.pop(name)
        if value is None:
            continue
        owner, _, field = join_path(path, name).rpartition(".")
        fluids = spec.setdefault("fluids", {})
        fluids[owner] = fluids.get(owner, {}) | {FLUID_NAMES[field]: value}


def _current_fluids(spec):
    """Return a format 2 spec with fluid fields of 0.2.0, reservoir parameters moved onto them."""
    spec["fluids"] = _fluid_names(spec.get("fluids", {}))
    if "boundary" in spec:
        spec["boundary"] = _fluid_names(spec["boundary"])
    _moved_fluid_params(spec, "", spec.get("params", {}))
    for name, entry in _entries_of(spec.get("modules", {})):
        _moved_fluid_params(spec, name, entry.get("params", {}))
    if not spec["fluids"]:
        del spec["fluids"]
    for entries in spec.get("param_history", {}).values():
        for entry in entries:
            entry["params"] = {k: v for k, v in entry["params"].items() if k not in FLUID_NAMES}
    return spec


def _entries_of(modules, prefix=""):
    """Yield ``(path, entry)`` of the module entries of a spec, looking through groups."""
    for name, entry in modules.items():
        path = join_path(prefix, name)
        yield path, entry
        yield from _entries_of(entry.get("modules", {}), path)


def _current_boilers(spec):
    """Return a spec with the boilers of 0.2.0: an electric one, or a gas one on a grid."""
    for entries in spec.get("param_history", {}).values():
        for entry in entries:
            entry["params"].pop("fuel_type", None)
    fed = {item["target"] for item in spec.get("connections", [])}
    for path, entry in list(_entries_of(spec.get("modules", {}))):
        fuel = entry.get("params", {}).pop("fuel_type", "gas")
        if fuel == "electric":
            entry["type"] = "ElectricBoiler"
        if entry.get("type") in ("Boiler", "CHP") and f"{path}.fuel_in" not in fed:
            grid = f"{path.replace('.', '_')}_grid"
            spec["modules"][grid] = {"type": "GasGrid", "params": {}}
            spec["connections"].append({"source": f"{grid}.gas_out", "target": f"{path}.fuel_in"})
    return spec


def _named_ports(spec):
    """Return a format 2 spec with the ports that were automatic plant ports before 0.2.0 named.

    Each free port keeps the name it had, ``<path with underscores>_<port>``, so a stored plant
    keeps its bindings. A spec that does not read is returned as it is, for ``validate`` to report.
    """
    plant, _ = reader.build(Plant, spec)
    if not isinstance(plant, Plant):
        return spec
    for side, path, port in plant._unconnected_ports():
        name = f"{path.replace('.', '_')}_{port}"
        spec.setdefault(side, {})[name] = join_path(path, port)
    return spec


def migrate(old):
    """Convert a format 1 plant file to a format 2 spec; a spec is returned as a copy.

    A format 2 spec gets the current port names (``RENAMED_PORTS``) and, written before 0.2.0,
    explicit names for its free ports, the fluid fields of 0.2.0 and the reservoir
    ``liquid_density`` and ``liquid_viscosity`` on the module's fluid;
    a ``Boiler`` of ``fuel_type="electric"`` becomes an ``ElectricBoiler``, and a gas ``Boiler`` or
    a ``CHP`` without a ``fuel_in`` gets a ``GasGrid``.

    A tree whose root class is a shipped plant takes that plant's wiring, with the stored
    values filled in; any other root is written as a handwritten root with flat dotted params.
    Failures raise ``ValidationError`` with code ``migration_failed``.
    """
    if isinstance(old, dict) and old.get("format") == FORMAT:
        return _named_ports(_current_boilers(_current_fluids(_current_ports(deepcopy(old)))))
    try:
        return _convert(old)
    except GeminiError:
        raise
    except (KeyError, TypeError, AttributeError, ValueError) as error:
        raise _failed(f"plant file: {type(error).__name__}: {error}") from error
