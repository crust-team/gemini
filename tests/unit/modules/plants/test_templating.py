"""Template filling: listing, filling with parameters, leaving units out and validation."""

import pytest

import gemini as gm
from gemini.modules.plants import library, templating


def _chain_template():
    """Return a template of three filters in series, the middle one optional."""
    return {
        "title": "Chain",
        "description": "Three filters in series.",
        "purpose": "both",
        "parameters": {
            "first.enabled": {"default": True, "unit": None, "description": "Keep the first."},
            "middle.enabled": {"default": True, "unit": None, "description": "Keep the middle."},
            "last.dp_nominal": {"default": None, "unit": "Pa", "description": "Pressure drop."},
        },
        "optional": {
            "middle": {"bypass": [{"source": "middle.inlet", "target": "middle.outlet"}]},
            "first": {"bypass": [{"source": "first.inlet", "target": "first.outlet"}]},
        },
        "spec": {
            "format": 2,
            "name": "Chain",
            "modules": {
                "first": {"type": "Filter", "params": {}},
                "middle": {"type": "Filter", "params": {}},
                "last": {"type": "Filter", "params": {}},
            },
            "connections": [
                {"source": "first.outlet", "target": "middle.inlet"},
                {"source": "middle.outlet", "target": "last.inlet"},
            ],
            "inlets": {"feed": "first.inlet"},
            "outlets": {"product": "last.outlet"},
            "outputs": {
                "drop": {"of": "middle.pressure_drop"},
                "last_drop": {"of": "last.pressure_drop"},
            },
            "bindings": {},
            "param_history": {},
        },
    }


def test_listing_names_every_template_with_its_summary():
    """Each entry has the name, title, description and a purpose of the fixed three."""
    rows = templating.listing()
    assert [row["name"] for row in rows] == templating.template_names()
    assert {"MultiWellPlant", "DistrictNetwork"} <= {row["name"] for row in rows}
    for row in rows:
        assert set(row) == {"name", "title", "description", "purpose"}
        assert row["purpose"] in {"heating", "cooling", "both"}


@pytest.mark.parametrize("name", templating.template_names())
def test_every_template_fills_with_its_defaults_into_a_valid_spec(name):
    """The defaults of each shipped template give a spec without problems."""
    spec = templating.fill(templating.load(name), {})
    assert gm.plants.validate(spec) == []


def test_default_sizes_build_the_shipped_plants():
    """The template defaults of a generated plant write the shipped spec file."""
    for name in ("MultiWellPlant", "DistrictNetwork"):
        assert gm.plants.from_template(name).to_spec() == library.shipped(name)


def test_a_parameter_sets_a_module_parameter_in_the_spec():
    """A name ``<module>.<parameter>`` states the value, unit strings included."""
    spec = templating.fill(_chain_template(), {"last.dp_nominal": "2 bar"})
    assert spec["modules"]["last"]["params"] == {"dp_nominal": "2 bar"}
    assert spec["modules"]["first"]["params"] == {}


def test_a_disabled_unit_leaves_with_its_wiring_and_the_bypass_closes_the_gap():
    """The middle filter, its connections and its output go; the bypass joins its neighbours."""
    spec = templating.fill(_chain_template(), {"middle.enabled": False})
    assert list(spec["modules"]) == ["first", "last"]
    assert spec["connections"] == [{"source": "first.outlet", "target": "last.inlet"}]
    assert list(spec["outputs"]) == ["last_drop"]
    assert spec["inlets"] == {"feed": "first.inlet"}


def test_a_disabled_end_unit_drops_its_ports_and_its_connections():
    """Without a bypass the neighbour's port becomes free and the plant port goes."""
    spec = templating.fill(_chain_template(), {"first.enabled": False})
    assert spec["inlets"] == {}
    assert spec["connections"] == [{"source": "middle.outlet", "target": "last.inlet"}]


def test_the_original_template_is_not_changed_by_filling():
    """Two fills of one template are independent."""
    template = _chain_template()
    templating.fill(template, {"middle.enabled": False, "last.dp_nominal": "1 bar"})
    assert template == _chain_template()


def test_unknown_names_and_wrong_flags_are_listed_together():
    """Every problem comes in one error; an unknown name carries close matches."""
    with pytest.raises(gm.errors.ValidationError) as error:
        gm.plants.from_template("MultiWellPlant", {"produsers": 3, "injectors": 0})
    assert "produsers" in str(error.value) and "producers" in error.value.suggestions
    with pytest.raises(gm.errors.UnknownNameError) as unknown:
        gm.plants.from_template("MultiWellPlnt")
    assert "MultiWellPlant" in unknown.value.suggestions


def test_a_template_value_of_the_wrong_unit_is_a_problem_of_the_spec(monkeypatch):
    """The filled spec is validated, so a wrong unit names the module and parameter."""
    template = _chain_template()
    monkeypatch.setattr(templating, "load", lambda name: template)
    with pytest.raises(gm.errors.ValidationError, match="last"):
        templating.from_template("Chain", {"last.dp_nominal": "2 m"})
    with pytest.raises(gm.errors.ValidationError, match="expected true or false"):
        templating.from_template("Chain", {"middle.enabled": "no"})
    assert templating.from_template("Chain", {"middle.enabled": False}).name == "Chain"


def test_neighbouring_units_leave_together_and_a_group_leaves_with_its_members():
    """Each unit closes its own gap in turn, so a run of optional units can all leave."""
    template = _chain_template()
    template["optional"]["last"] = {"bypass": [{"source": "last.inlet", "target": "last.outlet"}]}
    template["optional"]["tail"] = {"modules": ["middle", "last"]}
    template["parameters"]["tail.enabled"] = {"default": True, "unit": None, "description": "Tail."}
    spec = templating.fill(template, {"tail.enabled": False})
    assert list(spec["modules"]) == ["first"]
    assert spec["connections"] == [] and spec["outlets"] == {}
    separate = templating.fill(template, {"middle.enabled": False, "last.enabled": False})
    assert separate["modules"].keys() == spec["modules"].keys()


def test_a_bypass_joins_what_fed_the_inlet_to_what_the_outlet_fed():
    """Removing the middle of three filters joins the first outlet to the last inlet."""
    spec = templating.fill(_chain_template(), {"middle.enabled": False})
    assert spec["connections"] == [{"source": "first.outlet", "target": "last.inlet"}]


HEATING_COOLING_PRESETS = {
    "heating_only": {
        "heat_pump.enabled": False,
        "absorption_chiller.enabled": False,
        "adsorption_chiller.enabled": False,
        "compression_chiller.enabled": False,
        "cooling_loop.enabled": False,
    },
    "heating_absorption_cooling": {
        "heat_pump.enabled": False,
        "adsorption_chiller.enabled": False,
        "compression_chiller.enabled": False,
    },
    "heating_heat_pump_compression_cooling": {
        "absorption_chiller.enabled": False,
        "adsorption_chiller.enabled": False,
    },
    "heating_full_cooling": {"heat_pump.enabled": False},
}


@pytest.mark.parametrize("name", HEATING_COOLING_PRESETS)
def test_a_preset_is_the_heating_cooling_template_with_units_switched_off(name):
    """The preset spec equals the base template filled with the switches that name it."""
    preset = templating.fill(templating.load(name), {})
    base = templating.fill(templating.load("heating_cooling"), HEATING_COOLING_PRESETS[name])
    assert preset | {"name": base["name"]} == base
    assert gm.plants.from_spec(preset).to_spec() == preset
    kept = {key for key in templating.load(name)["parameters"]}
    assert kept <= set(templating.load("heating_cooling")["parameters"])


@pytest.mark.parametrize("name", templating.template_names())
def test_every_switch_and_parameter_of_a_template_names_something_in_its_spec(name):
    """Switches name optional entries, parameters name modules, bypasses name ports that exist."""
    template = templating.load(name)
    if "spec" not in template:
        return
    modules = set(template["spec"]["modules"])
    for parameter in template["parameters"]:
        unit, _, local = parameter.partition(".")
        if local == "enabled":
            assert unit in template["optional"]
        else:
            assert unit in modules
    for unit, entry in template["optional"].items():
        assert set(entry.get("modules", [unit])) <= modules
        for item in entry.get("bypass", []):
            assert item["source"].partition(".")[0] == item["target"].partition(".")[0] == unit
