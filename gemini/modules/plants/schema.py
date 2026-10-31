"""The JSON Schema of the plant spec, the input schema of a tool that builds plants."""

from gemini.modules._utils import registry
from gemini.modules.plants.factory import GROUPS

SECTION = {"type": "object", "additionalProperties": {"type": "object"}}
BINDINGS = {
    "type": "object",
    "description": (
        "Flat bindings of one module: a control, boundary, measured output or state name, or "
        "port.field of an inlet, to a column name or {column, unit}."
    ),
    "additionalProperties": {
        "anyOf": [
            {"type": "string"},
            {
                "type": "object",
                "required": ["column", "unit"],
                "additionalProperties": False,
                "properties": {"column": {"type": "string"}, "unit": {"type": "string"}},
            },
        ]
    },
}
PORT = {"type": "string", "pattern": r"^[^.\s]+(\.[^.\s]+)+$"}


def _module():
    return {
        "type": "object",
        "required": ["type"],
        "additionalProperties": False,
        "properties": {
            "type": {"type": "string", "enum": registry.names() + sorted(GROUPS)},
            "params": {"type": "object"},
            "modules": {"type": "object", "additionalProperties": {"$ref": "#/$defs/module"}},
        },
    }


def _connection():
    return {
        "type": "object",
        "required": ["source", "target"],
        "additionalProperties": False,
        "properties": {
            "source": PORT,
            "target": PORT,
            "kind": {"enum": ["state", None]},
        },
    }


def _output():
    return {
        "type": "object",
        "minProperties": 1,
        "maxProperties": 2,
        "additionalProperties": False,
        "properties": {
            "of": PORT,
            "field": {"type": "string"},
            "sum": {"type": "string"},
            "ratio": {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": 2},
            "difference": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 2,
                "maxItems": 2,
            },
        },
    }


def spec_schema():
    """Return the JSON Schema (draft 2020-12) of a format 2 plant spec."""
    ports = {"type": "object", "additionalProperties": PORT}
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "GEMINI plant spec",
        "type": "object",
        "required": ["format", "name", "modules", "connections", "bindings", "param_history"],
        "additionalProperties": False,
        "properties": {
            "format": {"const": 2},
            "name": {"type": "string"},
            "modules": {"type": "object", "additionalProperties": {"$ref": "#/$defs/module"}},
            "connections": {"type": "array", "items": _connection()},
            "inlets": ports,
            "outlets": ports,
            "outputs": {"type": "object", "additionalProperties": _output()},
            "fluids": SECTION,
            "boundary": SECTION,
            "bindings": {"type": "object", "additionalProperties": {"$ref": "#/$defs/bindings"}},
            "param_history": {
                "type": "object",
                "additionalProperties": {"type": "array", "items": {"type": "object"}},
            },
        },
        "$defs": {"module": _module(), "bindings": BINDINGS},
    }
