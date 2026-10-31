"""The JSON Schema of the plant spec."""

import json

import gemini as gm
from gemini.modules.plants._utils import library


def test_the_schema_is_plain_json_listing_every_module_type_and_group():
    """Types are an enumeration of the registry and the two groups."""
    schema = gm.plants.spec_schema()
    assert json.loads(json.dumps(schema)) == schema
    assert schema["$schema"].endswith("2020-12/schema")
    types = schema["$defs"]["module"]["properties"]["type"]["enum"]
    assert {"Filter", "Doublet", "ModuleDict", "ModuleList"} <= set(types)


def test_the_schema_requires_the_always_written_keys():
    """Format, name, modules, connections, bindings and param_history are required."""
    required = set(gm.plants.spec_schema()["required"])
    assert required == {"format", "name", "modules", "connections", "bindings", "param_history"}


def test_the_schema_accepts_only_the_keys_a_spec_writes():
    """Every key a built plant writes is declared."""
    plant = library.build("DoubletHeatPlant")
    assert set(plant.to_spec()) <= set(gm.plants.spec_schema()["properties"])
