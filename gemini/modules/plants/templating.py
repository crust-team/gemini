"""Plant templates: a spec with parameters, optional units and a generator for a variable size.

A template file in ``templates/`` holds ``title``, ``description``, ``purpose`` (``heating``,
``cooling`` or ``both``), ``parameters`` (name to ``default``, ``unit`` and ``description``),
``optional`` (unit id to ``bypass`` and ``modules``) and either a ``spec`` or the name of a
``generator`` in ``generators.py``.

A parameter of a ``spec`` template is named ``"<module id>.<parameter>"``, with a dotted
parameter path for a nested child, or ``"<module id>.enabled"``. Filling the template sets the
parameters in the spec and removes every disabled unit with its connections, ports and outputs, so
the result is a plain spec with no switch left. A ``generator`` template passes its parameters to
the generator as arguments.

An optional unit is a module id, or a group of ``modules`` that one switch removes together. Its
``bypass`` lists ``{"source": "<id>.<inlet>", "target": "<id>.<outlet>"}``, one per circuit that
runs through the unit: when the unit leaves, what fed that inlet is connected to what that outlet
fed, so the gap closes and neighbouring units can leave together. A port of a removed unit that
has no such partner is dropped, and so is a plant port or output that named the unit; keep plant
ports on modules that stay.
"""

from copy import deepcopy
from pathlib import Path

from gemini.errors import ValidationError
from gemini.errors.base import reported
from gemini.modules._utils.serialization import located
from gemini.modules.plants import generators
from gemini.modules.plants.spec import from_spec, validate
from gemini.utils.files import read_json
from gemini.utils.strings import close_matches, did_you_mean, join_names

TEMPLATES = Path(__file__).parent / "templates"
GENERATORS = {
    "multi_well_spec": generators.multi_well_spec,
    "district_network_spec": generators.district_network_spec,
}
ENABLED = "enabled"
SUMMARY_KEYS = ("title", "description", "purpose")
SECTIONS = ("fluids", "boundary", "bindings", "param_history")


def template_names():
    """Return the names of the shipped templates, sorted."""
    return sorted(path.stem for path in TEMPLATES.glob("*.json"))


def load(name):
    """Return the template file ``name``; an unknown name raises with close matches."""
    names = template_names()
    if name not in names:
        raise ValidationError(
            f"templates: unknown template {name!r}; valid: {join_names(names)}"
            f"{did_you_mean(name, names)}",
            path=name,
            suggestions=close_matches(name, names),
            code="unknown_name",
        )
    return read_json(TEMPLATES / f"{name}.json")


def listing():
    """Return ``[{name, title, description, purpose}]`` of every template."""
    return [{"name": name} | _summary(load(name)) for name in template_names()]


def _summary(template):
    return {key: template[key] for key in SUMMARY_KEYS}


def defaults(template):
    """Return the default value of every parameter of ``template``."""
    return {name: item["default"] for name, item in template["parameters"].items()}


def _unknown_names(template, given):
    declared = template["parameters"]
    return [
        located(
            f"parameters.{name}",
            ValidationError(
                f"unknown parameter {name!r}; valid: {join_names(declared)}"
                f"{did_you_mean(name, declared)}",
                suggestions=close_matches(name, declared),
                code="unknown_name",
            ),
        )
        for name in given
        if name not in declared
    ]


def _not_flags(given):
    return [
        located(
            f"parameters.{name}",
            ValidationError(f"{name} = {value!r}; expected true or false", code="invalid_value"),
        )
        for name, value in given.items()
        if name.endswith(f".{ENABLED}") and not isinstance(value, bool)
    ]


def _set_parameters(spec, values):
    """Set the stated parameters in ``spec`` and return the ids of the disabled units."""
    disabled = []
    for name, value in values.items():
        unit, _, local = name.partition(".")
        if local != ENABLED and value is not None:
            spec["modules"][unit].setdefault("params", {})[local] = value
        if local == ENABLED and not value:
            disabled.append(unit)
    return disabled


def _touches(end, gone):
    return end.partition(".")[0] in gone


def _expanded(template, disabled):
    """Return the module ids of the disabled switches, groups opened, each once."""
    members = []
    for unit in disabled:
        for module in template["optional"].get(unit, {}).get("modules", [unit]):
            if module not in members:
                members.append(module)
    return members


def _bridge(connections, item):
    """Return the connection that joins what feeds ``item["source"]`` to what its target feeds."""
    feeding = [entry for entry in connections if entry["target"] == item["source"]]
    leaving = [entry for entry in connections if entry["source"] == item["target"]]
    if not (feeding and leaving):
        return []
    return [{"source": feeding[0]["source"], "target": leaving[0]["target"]}]


def _remove_connections(spec, template, members):
    """Remove each module in turn from the connections, closing the gap with its bypass."""
    connections = spec["connections"]
    for unit in members:
        bypass = template["optional"].get(unit, {}).get("bypass", [])
        joined = [entry for item in bypass for entry in _bridge(connections, item)]
        connections = [
            entry
            for entry in connections
            if not (_touches(entry["source"], {unit}) or _touches(entry["target"], {unit}))
        ] + joined
    spec["connections"] = connections


def _kept_ends(end, gone):
    """Return the ends of a plant port that survive, a list when several share it."""
    if isinstance(end, list):
        return [item for item in end if not _touches(item, gone)]
    return None if _touches(end, gone) else end


def _remove_ports(spec, gone):
    for side in ("inlets", "outlets"):
        if side in spec:
            kept = {name: _kept_ends(end, gone) for name, end in spec[side].items()}
            spec[side] = {name: end for name, end in kept.items() if end}


def _remove_outputs(spec, gone):
    if "outputs" not in spec:
        return
    outputs = spec["outputs"]
    dropped = {name for name, item in outputs.items() if _touches(item.get("of", ""), gone)}
    dropped |= {name for name, item in outputs.items() if dropped & set(item.get("ratio", ()))}
    spec["outputs"] = {name: item for name, item in outputs.items() if name not in dropped}


def _remove_units(spec, template, disabled):
    members = _expanded(template, disabled)
    gone = set(members)
    for unit in members:
        del spec["modules"][unit]
    _remove_connections(spec, template, members)
    _remove_ports(spec, gone)
    _remove_outputs(spec, gone)
    for section in SECTIONS:
        if section in spec:
            spec[section] = {
                path: item for path, item in spec[section].items() if not _touches(path, gone)
            }


def fill(template, given):
    """Return the plain spec of ``template`` with the parameters ``given`` over the defaults."""
    values = defaults(template) | given
    if "generator" in template:
        return GENERATORS[template["generator"]](**values)
    spec = deepcopy(template["spec"])
    _remove_units(spec, template, _set_parameters(spec, values))
    return spec


def _filled(template, given):
    try:
        return fill(template, given), []
    except ValidationError as error:
        if error.code != "invalid_design":
            raise
        return None, [located("parameters", ValidationError(str(error), code="out_of_bounds"))]


def from_template(name, parameters=None):
    """Return the plant of template ``name`` with ``parameters`` over the template defaults.

    ``parameters`` maps a name from the template's ``parameters`` to a value, unit strings
    accepted. Every problem is listed in one ``ValidationError``; unknown names carry close
    matches in ``suggestions``.
    """
    template, given = load(name), dict(parameters or {})
    items = _unknown_names(template, given) + _not_flags(given)
    if not items:
        spec, items = _filled(template, given)
    if not items:
        items = validate(spec)
    reported(items, "raise")
    return from_spec(spec)
