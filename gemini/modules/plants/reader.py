"""Read a format 2 spec into a plant, collecting every problem with its path in the spec."""

from copy import deepcopy

from gemini.errors import GeminiError, ValidationError
from gemini.errors.base import reported
from gemini.modules import registry
from gemini.modules.plants import outputs
from gemini.modules.plants.factory import make_module
from gemini.modules.plants.plan import is_group, unconnected_port
from gemini.modules.plants.writer import baseline_of
from gemini.modules.serialization import (
    SECTIONS,
    Report,
    format_error,
    located,
    read_params,
    read_sections,
)
from gemini.utils.strings import close_matches, did_you_mean, join_path

TYPES = {
    "name": str,
    "type": str,
    "modules": dict,
    "connections": list,
    "inlets": dict,
    "outlets": dict,
    "outputs": dict,
    "params": dict,
    "fluids": dict,
    "boundary": dict,
    "bindings": dict,
    "param_history": dict,
}
KEYS = ("format", *TYPES)


def _shape(spec, report):
    """Return ``spec`` without the keys that are unknown or of the wrong JSON type."""
    clean = {}
    for key, value in spec.items():
        if key not in KEYS:
            error = ValidationError(
                f"unknown key {key!r}; valid: {', '.join(KEYS)}{did_you_mean(key, KEYS)}",
                path=key,
                code="invalid_format",
                suggestions=close_matches(key, KEYS),
            )
            report.items.append(located("", error))
        elif key in TYPES and not isinstance(value, TYPES[key]):
            error = ValidationError(
                f"{key} = {type(value).__name__}; expected {TYPES[key].__name__}",
                path=key,
                code="invalid_format",
            )
            report.items.append(located("", error))
        else:
            clean[key] = value
    return clean


def _entry(plant, prefix, name, entry, report, path):
    with report.guard(path):
        if not isinstance(entry, dict) or not isinstance(entry.get("type"), str):
            raise ValidationError(
                f"{name}: expected {{type, params}}", path="type", code="invalid_format"
            )
        key = join_path(prefix, name)
        try:
            module, _ = make_module(entry["type"])
        except GeminiError:
            report.broken.add(key)
            raise
        if is_group(module):
            plant._attach(key, module, None, {})
            for child, item in entry.get("modules", {}).items():
                _entry(plant, key, child, item, report, f"{path}.modules.{child}")
            return
        baseline = baseline_of(module)
        for pname, value in entry.get("params", {}).items():
            with report.guard(f"{path}.params.{pname}"):
                module.set_params("", {pname: value})
        plant._attach(key, module, deepcopy(entry.get("params")), baseline)


def _connection(plant, item, report):
    if not isinstance(item, dict) or not all(
        isinstance(item.get(k), str) for k in ("source", "target")
    ):
        raise ValidationError("expected {source, target, kind?}", path="", code="invalid_format")
    usable = [end for end in ("source", "target") if not report.skips(item[end])]
    if len(usable) == 2:
        plant._link(item["source"], item["target"], item.get("kind"), explicit=True)
        return
    for end in usable:
        plant._candidates(item[end], end, explicit=True)


def _port(plant, side, name, end, report):
    if not isinstance(end, str):
        raise ValidationError(f"{name}: expected 'path.port'", code="invalid_format")
    if report.skips(end):
        return
    if side == "inlets":
        plant._link(name, end, None, explicit=True)
    else:
        plant._link(end, name, None, explicit=True)


def _outputs(plant, specs, report):
    plant._output_specs = {}
    plant._refresh()
    for name, spec in outputs.ordered(specs):
        with report.guard(f"outputs.{name}"):
            if not isinstance(spec, dict):
                raise ValidationError(f"{name}: expected a mapping", code="invalid_format")
            if report.skips(spec.get("of", "")):
                continue
            outputs.declare_output(plant, name, spec)
            plant._output_specs[name] = deepcopy(spec)


def _ends(spec):
    """Return every port the spec names, also those of an entry that failed to read."""
    connections = [item for item in spec.get("connections", []) if isinstance(item, dict)]
    ends = {item.get(end) for item in connections for end in ("source", "target")}
    return ends | set(spec.get("inlets", {}).values()) | set(spec.get("outlets", {}).values())


def _check_ports(plant, spec, report):
    """Report each port no entry of ``spec`` names; a named port that failed has its problem."""
    named = _ends(spec)
    for _, path, port in plant._unconnected_ports():
        end = join_path(path, port)
        if end not in named and not report.skips(end):
            with report.guard(""):
                raise unconnected_port(end)


def populate(plant, spec, report):
    """Add the modules, connections, ports, outputs and sections of ``spec`` to ``plant``."""
    for name, entry in spec.get("modules", {}).items():
        _entry(plant, "", name, entry, report, f"modules.{name}")
    for index, item in enumerate(spec.get("connections", [])):
        with report.guard(f"connections[{index}]"):
            _connection(plant, item, report)
    for side in ("inlets", "outlets"):
        for name, end in spec.get(side, {}).items():
            with report.guard(f"{side}.{name}"):
                _port(plant, side, name, end, report)
    _check_ports(plant, spec, report)
    if "outputs" in spec:
        _outputs(plant, spec["outputs"], report)
    read_sections(plant, spec, report)
    plant._sections = {key: deepcopy(spec.get(key, {})) for key in SECTIONS}


def _handwritten(spec, report):
    with report.guard("type"):
        found = registry.get(spec["type"])
        if not isinstance(found, type):
            return found
        module = found()
        read_params(module, spec.get("params", {}), report)
        read_sections(module, spec, report)
        return module
    return None


def build(cls, spec):
    """Return ``(plant or None, problems)`` for a spec; problems are empty when it is valid."""
    report = Report()
    error = format_error(spec)
    if error is not None:
        report.items.append(located("", error))
        return None, report.items
    spec = _shape(spec, report)
    if "type" in spec:
        plant = _handwritten(spec, report)
    else:
        plant = cls._empty(spec.get("name", "plant"))
        populate(plant, spec, report)
    return plant, report.items


def problems(cls, spec):
    """Return every problem of ``spec`` as ``[{path, code, message, suggestions}]``."""
    return build(cls, spec)[1]


def read(cls, spec):
    """Return the plant of ``spec``, or raise a ``ValidationError`` that carries every problem."""
    error = format_error(spec)
    if error is not None:
        raise error
    plant, items = build(cls, spec)
    reported(items, "raise")
    return plant
