"""The JSON Schema of a demand profile as a document."""


def profile_schema():
    """Return the JSON Schema (draft 2020-12) of what ``profiles.get`` returns, as plain JSON.

    The document carries a frame of ``get`` to another repository: its ``name``, the ``description``
    and ``source`` of ``attrs``, the ``columns`` with their ``unit`` and ``quantity`` of ``attrs``,
    the UTC ``time`` stamps of the index and the ``values`` per column, as long as ``time``.
    """
    column = {
        "type": "object",
        "required": ["unit", "quantity"],
        "additionalProperties": False,
        "properties": {
            "unit": {"type": "string"},
            "quantity": {"type": "string"},
            "description": {"type": "string"},
        },
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Demand profile",
        "type": "object",
        "required": ["name", "description", "source", "columns", "time", "values"],
        "additionalProperties": False,
        "properties": {
            "name": {"type": "string"},
            "description": {"type": "string"},
            "source": {"type": "string", "description": "Where the data comes from."},
            "columns": {"type": "object", "minProperties": 1, "additionalProperties": column},
            "time": {
                "type": "array",
                "minItems": 1,
                "items": {"type": "string", "format": "date-time"},
            },
            "values": {
                "type": "object",
                "additionalProperties": {"type": "array", "items": {"type": ["number", "null"]}},
            },
        },
    }
