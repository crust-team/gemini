"""A small JSON Schema checker for the keywords of ``gemini/schemas``; no new dependency."""

import re

TYPES = {
    "object": dict,
    "array": list,
    "string": str,
    "boolean": bool,
    "null": type(None),
    "number": (int, float),
    "integer": int,
}


def _has_type(value, name):
    if isinstance(value, bool):
        return name == "boolean"
    return isinstance(value, TYPES[name])


def _resolve(reference, root):
    node = root
    for part in reference.removeprefix("#/").split("/"):
        node = node[part]
    return node


def _object_problems(value, schema, root, path):
    problems = [f"{path}: missing {key}" for key in schema.get("required", ()) if key not in value]
    properties = schema.get("properties", {})
    extra = schema.get("additionalProperties", True)
    for key, item in value.items():
        if key in properties:
            problems += check(item, properties[key], root, f"{path}.{key}")
        elif extra is False:
            problems.append(f"{path}: unexpected {key}")
        elif isinstance(extra, dict):
            problems += check(item, extra, root, f"{path}.{key}")
    if len(value) < schema.get("minProperties", 0):
        problems.append(f"{path}: too few properties")
    if len(value) > schema.get("maxProperties", len(value)):
        problems.append(f"{path}: too many properties")
    return problems


def _array_problems(value, schema, root, path):
    problems = []
    if len(value) < schema.get("minItems", 0):
        problems.append(f"{path}: too few items")
    if len(value) > schema.get("maxItems", len(value)):
        problems.append(f"{path}: too many items")
    items = schema.get("items", {})
    for index, item in enumerate(value):
        problems += check(item, items, root, f"{path}[{index}]")
    return problems


def _scalar_problems(value, schema, path):
    problems = []
    if "const" in schema and value != schema["const"]:
        problems.append(f"{path}: expected {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        problems.append(f"{path}: {value!r} is not in the enum")
    if "pattern" in schema and isinstance(value, str) and not re.search(schema["pattern"], value):
        problems.append(f"{path}: {value!r} does not match {schema['pattern']}")
    return problems


def check(value, schema, root=None, path="$"):
    """Return every problem of ``value`` against ``schema``; empty when it is valid."""
    root = schema if root is None else root
    if "$ref" in schema:
        return check(value, _resolve(schema["$ref"], root), root, path)
    if "anyOf" in schema and all(check(value, item, root, path) for item in schema["anyOf"]):
        return [f"{path}: fits no variant"]
    kinds = schema.get("type")
    kinds = [kinds] if isinstance(kinds, str) else kinds
    if kinds is not None and not any(_has_type(value, kind) for kind in kinds):
        return [f"{path}: {type(value).__name__} is not {kinds}"]
    problems = _scalar_problems(value, schema, path)
    if isinstance(value, dict):
        problems += _object_problems(value, schema, root, path)
    if isinstance(value, list):
        problems += _array_problems(value, schema, root, path)
    return problems
