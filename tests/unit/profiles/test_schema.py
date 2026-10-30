"""The JSON Schema of a profile file."""

import json

import gemini as gm
from tests.unit.profiles.test_library import PROFILE


def test_the_schema_names_every_key_of_a_profile_file():
    """The schema is draft 2020-12, plain JSON, and requires the keys the reader reads."""
    schema = gm.profiles.profile_schema()
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert json.loads(json.dumps(schema)) == schema
    assert set(schema["required"]) == set(schema["properties"]) == set(PROFILE)
    assert schema["additionalProperties"] is False


def test_a_column_needs_a_unit_and_a_quantity():
    """Units are never implied: the column schema requires them."""
    column = gm.profiles.profile_schema()["properties"]["columns"]["additionalProperties"]
    assert column["required"] == ["unit", "quantity"]
    assert set(column["properties"]) == {"unit", "quantity", "description"}
