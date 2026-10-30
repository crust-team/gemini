"""What a module says about itself as plain JSON: ``describe``, its schema, its checks.

``description`` is imported by ``module.py``, so it never imports it: a module is used through
its public methods only.
"""

from copy import deepcopy

from pydantic import ValidationError as PydanticValidationError

from gemini.core.types.declarations import UNSET
from gemini.errors import DeclarationError, MissingValueError, UnitError
from gemini.utils.jsonable import to_plain
from gemini.utils.strings import close_matches, did_you_mean, first_paragraph

STREAM_FIELDS = {"m_dot": {"unit": "kg/s"}, "T": {"unit": "K"}, "p": {"unit": "Pa"}}
"""The fields every port stream shows and their SI units."""

SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"

_BOUND_CODES = {"greater_than", "greater_than_equal", "less_than", "less_than_equal"}
_NUMBER_TYPES = ("number", "integer")
_MINIMUM_KEYS = ("ge", "gt")
_MAXIMUM_KEYS = ("le", "lt")
_EXCLUSIVE_KEYS = {"gt": "exclusiveMinimum", "lt": "exclusiveMaximum"}
_INCLUSIVE_KEYS = {"ge": "minimum", "le": "maximum"}


def _value_schema(declaration):
    """Return the JSON schema of the declared value: the non-null variant, a list's items."""
    schema = declaration.schema
    variants = schema.get("anyOf", [schema])
    value_schema = next((item for item in variants if item.get("type") != "null"), schema)
    return value_schema.get("items", value_schema)


def _enum(declaration):
    """Return the allowed values of a ``Literal`` kind, or ``None``."""
    value_schema = _value_schema(declaration)
    if "const" in value_schema:
        return [value_schema["const"]]
    return value_schema.get("enum")


def _closest_limit(declaration, keys):
    """Return the value of the first of ``keys`` that the declaration limits, else ``None``."""
    limits = declaration.limits()
    return next((limits[key] for key in keys if key in limits), None)


def _default(declaration):
    """Return the default as plain JSON; ``UNSET`` is ``None``."""
    if declaration.default is UNSET:
        return None
    return to_plain(declaration.default_value())


def _entry(declaration):
    """Describe one declaration; a missing item is ``None``.

    ``minimum`` and ``maximum`` are the closest limit, so a strict bound (``gt``, ``lt``) shows
    as the bound itself: the value may not reach it.
    """
    return {
        "type": declaration.value_type(),
        "unit": declaration.unit,
        "quantity": declaration.quantity,
        "default": _default(declaration),
        "minimum": _closest_limit(declaration, _MINIMUM_KEYS),
        "maximum": _closest_limit(declaration, _MAXIMUM_KEYS),
        "enum": _enum(declaration),
        "description": declaration.description,
        "section": declaration.section,
    }


def _entries(declarations):
    return {name: _entry(declaration) for name, declaration in declarations.items()}


def _ports(declarations):
    return {
        name: {
            "stream": declaration.stream,
            "fields": {k: dict(v) for k, v in STREAM_FIELDS.items()},
        }
        for name, declaration in declarations.items()
    }


def _outputs(declarations):
    return {
        name: {
            "unit": declaration.unit,
            "kind": declaration.quantity if declaration.additive else None,
            "soft_sensor": declaration.soft_sensor,
        }
        for name, declaration in declarations.items()
    }


def _connections(module):
    """Return the wiring a plant exposes through ``connection_list()``; handwritten ones have none.

    Wiring of a handwritten composite is code, so it cannot be listed.
    """
    listing = getattr(type(module), "connection_list", None)
    return to_plain(listing(module)) if listing is not None else []


def _type_name(module):
    """Return the class name; a plant (it lists connections) shows its given name."""
    if hasattr(type(module), "connection_list"):
        return module.name
    return type(module).__name__


def _current_inputs(declarations):
    values = {}
    for path, declaration in declarations.items():
        try:
            values[path] = to_plain(getattr(declaration.owner, declaration.name))
        except MissingValueError:
            continue
    return values


def _values(module):
    """Return the current parameters, controls and boundaries; unset ones are left out.

    Values of descendants are keyed by their dotted path below this module.
    """
    parameters = {
        path: to_plain(parameter.value)
        for path, parameter in module.named_parameters()
        if parameter.initialized
    }
    return {
        "parameters": parameters,
        "controls": _current_inputs(module.controls()),
        "boundaries": _current_inputs(module.boundaries()),
    }


def describe(module):
    """Return the description of a module as plain JSON.

    The keys are ``name``, ``type``, ``category``, ``summary`` (first paragraph of the docstring),
    ``doc``, ``parameters``, ``controls``, ``boundaries``, ``measured``, ``state``, ``inlets``,
    ``outlets``, ``outputs``, ``children``, ``connections`` and ``values``. Each entry of the
    first five has ``type``, ``unit``, ``quantity``, ``default``, ``minimum``, ``maximum``,
    ``enum``, ``description`` and ``section``.

    - ``measured`` lists the outputs of the module itself: replay accepts a measured binding for
      any of them and compares it with the output of the same name.
    - ``minimum`` and ``maximum`` are the closest limit, strict (``gt``, ``lt``) or not.
    - ``stream`` of a port is ``None`` for a port that takes any stream.
    - ``kind`` of an output is its additive quantity name, else ``None``.
    - ``children`` maps a child name to its type; ``connections`` lists
      ``{source, target, stream, kind}`` for a plant and is empty for a handwritten composite.
    - ``values`` holds the current parameter, control and boundary values; a class gives the
      defaults of a new instance.
    """
    doc = type(module).__doc__ or ""
    outputs = module.outputs(recurse=False)
    return {
        "name": module.path,
        "type": _type_name(module),
        "category": module.category,
        "summary": first_paragraph(doc.strip()),
        "doc": doc.strip(),
        "parameters": _entries(dict(module.named_parameters(recurse=False))),
        "controls": _entries(module.controls(recurse=False)),
        "boundaries": _entries(module.boundaries(recurse=False)),
        "measured": _entries(outputs),
        "state": _entries(module.states(recurse=False)),
        "inlets": _ports(module.inlets()),
        "outlets": _ports(module.outlets()),
        "outputs": _outputs(outputs),
        "children": {name: _type_name(child) for name, child in module.named_children()},
        "connections": _connections(module),
        "values": _values(module),
    }


def _property_bounds(declaration):
    bounds = {}
    for key, name in (_INCLUSIVE_KEYS | _EXCLUSIVE_KEYS).items():
        if key in declaration.limits():
            bounds[name] = declaration.limits()[key]
    return bounds


def _item_schema(declaration):
    """Return the schema of one value without unit strings; a list keeps its own schema."""
    schema = declaration.schema
    variants = schema.get("anyOf", [schema])
    value_schema = next((item for item in variants if item.get("type") != "null"), schema)
    if value_schema.get("type") == "array":
        return deepcopy(value_schema)
    item = {"type": declaration.value_type()} if declaration.value_type() else {}
    if declaration.value_type() in _NUMBER_TYPES:
        item |= _property_bounds(declaration)
    if _enum(declaration) is not None:
        item["enum"] = _enum(declaration)
    return item


def _value_variants(declaration):
    """Return the ``anyOf`` variants of a value: a number may also be a unit string."""
    variants = [_item_schema(declaration)]
    if declaration.unit and declaration.value_type() in _NUMBER_TYPES and not _is_list(declaration):
        variants.append({"type": "string"})
    if declaration.accepts_none():
        variants.append({"type": "null"})
    return variants


def _is_list(declaration):
    schema = declaration.schema
    return any(item.get("type") == "array" for item in schema.get("anyOf", [schema]))


def _property(declaration):
    property_schema = {}
    variants = _value_variants(declaration)
    if len(variants) == 1:
        property_schema |= variants[0]
    else:
        property_schema["anyOf"] = variants
    for key, value in (
        ("unit", declaration.unit),
        ("quantity", declaration.quantity),
        ("description", declaration.description),
    ):
        if value is not None:
            property_schema[key] = value
    if declaration.default is not UNSET:
        property_schema["default"] = _default(declaration)
    return property_schema


def parameter_schema(module):
    """Return the JSON Schema (draft 2020-12) of a module's parameters.

    One property per parameter, the parameters of children under their dotted path. A property
    carries the standard keywords (``type``, ``anyOf``, ``minimum``, ``maximum``,
    ``exclusiveMinimum``, ``exclusiveMaximum``, ``enum``, ``default``, ``description``) and, besides
    them, ``unit`` and ``quantity``. A number with a unit also accepts a unit string such as
    ``"150 m3/h"``. ``required`` lists the parameters that have no default.
    """
    declarations = dict(module.named_parameters())
    return {
        "$schema": SCHEMA_DIALECT,
        "title": _type_name(module),
        "type": "object",
        "properties": {path: _property(item) for path, item in declarations.items()},
        "required": [path for path, item in declarations.items() if item.default is UNSET],
        "additionalProperties": False,
    }


def _problem(path, message, code, suggestions=()):
    problem = {"path": path, "message": message, "code": code}
    if suggestions:
        problem["suggestions"] = list(suggestions)
    return problem


def _error_code(error):
    """Tell the classes of failure apart: a unit, a bound, or any other value."""
    cause = error.__cause__
    if isinstance(error, UnitError) or isinstance(cause, UnitError):
        return "invalid_unit"
    if isinstance(cause, PydanticValidationError):
        if any(item["type"] in _BOUND_CODES for item in cause.errors()):
            return "out_of_bounds"
    return "invalid_value"


def _check_value(name, declaration, value):
    try:
        declaration.validate(value)
    except (DeclarationError, UnitError) as error:
        return _problem(name, str(error), _error_code(error))
    return None


def validate_params(module, params):
    """Return every problem of ``params`` as ``[{path, message, code}]``; never raises for them.

    ``params`` maps a parameter name (dotted for a child's) to a number, a unit string or a
    value of the declared kind. The codes are ``unknown_name`` (with ``suggestions``),
    ``invalid_unit``, ``out_of_bounds`` and ``invalid_value``. The module is not changed.
    """
    declarations = dict(module.named_parameters())
    problems = []
    for name, value in params.items():
        if name not in declarations:
            message = f"{module.path}: unknown parameter {name!r}{did_you_mean(name, declarations)}"
            problems.append(
                _problem(name, message, "unknown_name", close_matches(name, declarations))
            )
            continue
        problem = _check_value(name, declarations[name], value)
        if problem is not None:
            problems.append(problem)
    return problems
