"""Module descriptions, schemas and parameter checks."""

import json

import gemini as gm

DESCRIPTION_KEYS = {
    "name",
    "type",
    "category",
    "summary",
    "doc",
    "parameters",
    "controls",
    "boundaries",
    "measured",
    "state",
    "inlets",
    "outlets",
    "outputs",
    "children",
    "connections",
}
ENTRY_KEYS = {
    "type",
    "unit",
    "quantity",
    "default",
    "minimum",
    "maximum",
    "enum",
    "description",
    "section",
}
SCHEMA_KEYWORDS = {
    "type",
    "anyOf",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "enum",
    "const",
    "default",
    "description",
    "unit",
    "quantity",
    "items",
    "prefixItems",
    "minItems",
    "maxItems",
    "title",
    "additive",
}
SCHEMA_TYPES = {"number", "integer", "string", "boolean", "array", "null", "object"}


def assert_plain_json(value):
    """Serialise without NaN or numpy types."""
    json.dumps(value, allow_nan=False)


def assert_valid_property(name, schema):
    """Check the keywords and types of one property schema, recursively."""
    assert set(schema) <= SCHEMA_KEYWORDS, f"{name}: {set(schema) - SCHEMA_KEYWORDS}"
    if "type" in schema:
        assert schema["type"] in SCHEMA_TYPES, name
    for variant in schema.get("anyOf", ()):
        assert_valid_property(name, variant)
    for key in ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum"):
        assert isinstance(schema.get(key, 0), (int, float)), name
    if "enum" in schema:
        assert isinstance(schema["enum"], list) and schema["enum"], name
    if isinstance(schema.get("items"), dict):
        assert_valid_property(name, schema["items"])
    for item in schema.get("prefixItems", ()):
        assert_valid_property(name, item)
    if "unit" in schema:
        assert isinstance(schema["unit"], str), name


def assert_valid_schema(schema):
    """Check the top level and every property of a parameter schema."""
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) <= set(schema["properties"])
    for name, property_schema in schema["properties"].items():
        assert_valid_property(name, property_schema)


def test_leaf_description_shape():
    """A leaf has the documented keys, entries, ports and outputs."""
    description = gm.modules.ESP.describe()
    assert set(description) - {"values"} == DESCRIPTION_KEYS
    assert description["name"] == "esp" and description["type"] == "ESP"
    assert description["category"] == "pump"
    assert description["summary"] == description["doc"].split("\n\n")[0]
    assert set(description["parameters"]["setting_depth"]) == ENTRY_KEYS
    efficiency = description["parameters"]["motor_efficiency"]
    assert (efficiency["minimum"], efficiency["maximum"], efficiency["unit"]) == (0, 1, "-")
    assert description["parameters"]["no_stages"]["default"] is None
    assert description["inlets"]["suction"]["stream"] == "brine"
    assert description["inlets"]["suction"]["fields"]["T"] == {"unit": "K"}
    assert description["outputs"]["electricity"] == {
        "unit": "W",
        "kind": "electricity",
        "soft_sensor": False,
    }
    assert description["outputs"]["head"]["soft_sensor"] is True
    assert description["children"] == {} and description["connections"] == []
    assert set(description["measured"]) == set(description["outputs"])


def test_instance_values_follow_the_module():
    """An instance reports current values and omits uninitialised ones."""
    esp = gm.modules.ESP()
    esp.update_params(no_stages=12)
    assert "frequency" not in esp.describe()["values"]["controls"]
    esp.set_inputs({"frequency": 50.0})
    values = esp.describe()["values"]
    assert values["parameters"]["no_stages"] == 12
    assert "head_coeff" not in values["parameters"]
    assert values["controls"]["frequency"] == 50.0


def test_composite_lists_children_and_dotted_values():
    """A composite names its children and nests their values by dotted path."""
    substation = gm.modules.HeatingSubstation()
    description = substation.describe()
    assert description["children"]
    assert all(isinstance(name, str) for name in description["children"].values())
    assert description["connections"] == []
    schema = substation.parameter_schema()
    assert any("." in name for name in schema["properties"])
    assert_valid_schema(schema)


def test_a_spec_plant_lists_its_connections():
    """A plant built from a spec names its children, its connections and dotted values."""
    doublet = gm.plants.get("Doublet")
    description = doublet.describe()
    assert list(description["children"]) == [
        "reservoir",
        "well",
        "esp",
        "riser",
        "injector",
        "sink",
    ]
    assert len(description["connections"]) == 4
    assert {item["source"] for item in description["connections"]} >= {"esp.discharge"}
    assert any("." in name for name in doublet.parameter_schema()["properties"])


def test_description_does_not_mutate():
    """Describing and validating leave the module as it was."""
    esp = gm.modules.ESP().update_params(no_stages=3)
    before = esp.state_dict()
    esp.describe()
    esp.parameter_schema()
    esp.validate_params({"no_stages": "5", "bogus": 1})
    assert esp.state_dict() == before


def test_every_module_serialises_and_has_a_valid_schema(module_class):
    """Each shipped module describes itself as plain JSON with a valid schema."""
    description = module_class.describe()
    assert set(description) == DESCRIPTION_KEYS
    assert_plain_json(description)
    schema = module_class.parameter_schema()
    assert_plain_json(schema)
    assert_valid_schema(schema)
    for section in ("parameters", "controls", "boundaries", "measured", "state"):
        assert all(set(entry) == ENTRY_KEYS for entry in description[section].values())


def test_schema_accepts_unit_strings_and_keeps_units():
    """A number with a unit is a number or a string; the unit stays on the property."""
    properties = gm.modules.ESP.parameter_schema()["properties"]
    depth = properties["setting_depth"]
    assert depth["unit"] == "m" and depth["quantity"] == "length"
    assert [variant["type"] for variant in depth["anyOf"]] == ["number", "string"]
    assert depth["anyOf"][0]["minimum"] == 0
    assert "no_stages" in gm.modules.ESP.parameter_schema()["required"]


def test_validate_params_accepts_valid_values_and_unit_strings():
    """Numbers and unit strings in the right dimension raise nothing."""
    assert gm.modules.ESP.validate_params({"no_stages": 12, "setting_depth": "1000 ft"}) == []


def test_validate_params_reports_every_problem():
    """Unknown names, units and bounds are all reported at once."""
    problems = gm.modules.ESP.validate_params(
        {"no_stage": 3, "setting_depth": "5 bar", "motor_efficiency": 1.5, "tubing": "x"}
    )
    by_path = {problem["path"]: problem for problem in problems}
    assert by_path["no_stage"]["code"] == "unknown_name"
    assert by_path["no_stage"]["suggestions"] == ["no_stages"]
    assert by_path["setting_depth"]["code"] == "invalid_unit"
    assert by_path["motor_efficiency"]["code"] == "out_of_bounds"
    assert by_path["tubing"]["code"] == "invalid_value"
    assert all(set(problem) >= {"path", "message", "code"} for problem in problems)
    assert {problem["code"] for problem in problems} <= set(gm.errors.CODES)
    assert_plain_json(problems)


def test_the_example_plant_describes_itself_with_its_values(shared_plant):
    """Pipe paths and every other stored value serialise, for the agent's ``read_plant``."""
    description = shared_plant.describe()
    assert json.dumps(description, allow_nan=False)
    assert "doublet.esp.no_stages" in description["values"]["parameters"]


def test_values_are_only_on_an_instance():
    """A class stores no values; an instance does."""
    assert "values" not in gm.modules.Valve.describe()
    assert "values" in gm.modules.Valve().describe()
