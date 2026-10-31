"""Write a built plant as its format 2 spec: structure, stated values kept as written."""

from copy import deepcopy

from gemini.errors import GeminiError
from gemini.modules._utils import design
from gemini.modules._utils.serialization import (
    FORMAT,
    keep_stated,
    plain_value,
    tree_params,
    write_sections,
)
from gemini.modules.plants._utils.plan import is_group
from gemini.utils.strings import join_path


def baseline_of(module):
    """Return the parameter values a module has before any value is stated, by dotted name."""
    return tree_params(module)


def type_name(module):
    """Return the registry name that rebuilds ``module``."""
    return module.name if hasattr(type(module), "_port_map") else type(module).__name__


def _same(module, name, stated, current):
    try:
        return keep_stated(stated, current, lambda value: _plain(module, name, value))
    except GeminiError:
        return None


def _plain(module, name, value):
    return plain_value(design.parameter(module, name).validate(value))


def params_spec(plant, key, module):
    """Return the ``params`` of one module: stated values while true, others that changed."""
    stated = plant._stated.get(key) or {}
    baseline = plant._baselines.get(key, {})
    derived = design.derived_names(module)
    result = {}
    for name, value in tree_params(module).items():
        if name in stated:
            kept = _same(module, name, stated[name], value)
            result[name] = kept if kept is not None else value
        elif name not in derived and (name not in baseline or baseline[name] != value):
            result[name] = value
    return result


def modules_spec(plant, container, prefix=""):
    """Return the ``modules`` mapping of ``container``, groups nested."""
    result = {}
    for name, child in container.named_children():
        key = join_path(prefix, name)
        entry = {"type": type_name(child)}
        if is_group(child):
            entry["modules"] = modules_spec(plant, child, key)
        else:
            params = params_spec(plant, key, child)
            if params or plant._stated.get(key) is not None:
                entry["params"] = params
        result[name] = entry
    return result


def _port_text(ends):
    """Return the ``"path.port"`` text of a plant port, a list when several ends share it."""
    if isinstance(ends, list):
        return [join_path(*end) for end in ends]
    return join_path(*ends)


def plant_spec(plant):
    """Return the format 2 spec of ``plant``."""
    spec = {
        "format": FORMAT,
        "name": plant.name,
        "modules": modules_spec(plant, plant),
        "connections": deepcopy(plant._connections),
    }
    for side in ("inlets", "outlets"):
        if plant._listed[side]:
            spec[side] = {name: _port_text(end) for name, end in plant._listed[side].items()}
    if plant._output_specs is not None:
        spec["outputs"] = deepcopy(plant._output_specs)
    return spec | write_sections(plant, plant._sections)
