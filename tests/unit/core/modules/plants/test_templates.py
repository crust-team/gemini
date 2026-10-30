"""Templates: listing, filling with parameters, leaving units out and validation."""

import pytest

import gemini as gm
from gemini.core.modules.plants import library, templates


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
            "middle": {"bypass": [{"source": "first.outlet", "target": "last.inlet"}]},
            "first": {"bypass": []},
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
    rows = templates.listing()
    assert [row["name"] for row in rows] == templates.template_names()
    assert {"MultiWellPlant", "DistrictNetwork"} <= {row["name"] for row in rows}
    for row in rows:
        assert set(row) == {"name", "title", "description", "purpose"}
        assert row["purpose"] in {"heating", "cooling", "both"}


def test_every_template_fills_with_its_defaults_into_a_valid_spec():
    """The defaults of each shipped template give a spec without problems."""
    for name in templates.template_names():
        spec = templates.fill(templates.load(name), {})
        assert gm.plants.validate(spec) == [], name


def test_default_sizes_build_the_shipped_plants():
    """The template defaults of a generated plant write the shipped spec file."""
    for name in ("MultiWellPlant", "DistrictNetwork"):
        assert gm.plants.from_template(name).to_spec() == library.shipped(name)


def test_a_parameter_sets_a_module_parameter_in_the_spec():
    """A name ``<module>.<parameter>`` states the value, unit strings included."""
    spec = templates.fill(_chain_template(), {"last.dp_nominal": "2 bar"})
    assert spec["modules"]["last"]["params"] == {"dp_nominal": "2 bar"}
    assert spec["modules"]["first"]["params"] == {}


def test_a_disabled_unit_leaves_with_its_wiring_and_the_bypass_closes_the_gap():
    """The middle filter, its connections and its output go; the bypass joins its neighbours."""
    spec = templates.fill(_chain_template(), {"middle.enabled": False})
    assert list(spec["modules"]) == ["first", "last"]
    assert spec["connections"] == [{"source": "first.outlet", "target": "last.inlet"}]
    assert list(spec["outputs"]) == ["last_drop"]
    assert spec["inlets"] == {"feed": "first.inlet"}


def test_a_disabled_end_unit_drops_its_ports_and_its_connections():
    """Without a bypass the neighbour's port becomes free and the plant port goes."""
    spec = templates.fill(_chain_template(), {"first.enabled": False})
    assert spec["inlets"] == {}
    assert spec["connections"] == [{"source": "middle.outlet", "target": "last.inlet"}]


def test_the_original_template_is_not_changed_by_filling():
    """Two fills of one template are independent."""
    template = _chain_template()
    templates.fill(template, {"middle.enabled": False, "last.dp_nominal": "1 bar"})
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
    monkeypatch.setattr(templates, "load", lambda name: template)
    with pytest.raises(gm.errors.ValidationError, match="last"):
        templates.from_template("Chain", {"last.dp_nominal": "2 m"})
    with pytest.raises(gm.errors.ValidationError, match="expected true or false"):
        templates.from_template("Chain", {"middle.enabled": "no"})
    assert templates.from_template("Chain", {"middle.enabled": False}).name == "Chain"
