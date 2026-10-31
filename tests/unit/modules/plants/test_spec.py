"""The public spec functions: round trip, JSON safety and the shared name pair."""

import json

import pytest

import gemini as gm
from tests.fixtures import ROOT

PLANT_FILE = ROOT / "examples/shared/doublet_heat/plant.json"


def test_from_dict_and_from_spec_are_one_function():
    """The plant file and the spec are the same document and the same function."""
    assert gm.plants.from_dict is gm.plants.from_spec
    assert gm.plants.validate({"format": 2, "name": "x", "modules": {}, "connections": []}) == []


def test_the_stored_plant_file_round_trips_exactly():
    """``to_spec(from_spec(x)) == x`` for the migrated example plant, JSON-safe."""
    spec = json.loads(PLANT_FILE.read_text())
    plant = gm.plants.from_spec(spec)
    assert plant.to_spec() == spec
    assert plant.to_dict() == spec
    assert json.loads(json.dumps(plant.to_spec(), allow_nan=False)) == spec


def test_a_spec_with_unit_strings_and_sections_round_trips_exactly():
    """Unit strings stay as written; fluids, history and bindings are kept."""
    spec = {
        "format": 2,
        "name": "DoubletHeatPlant",
        "modules": {
            "pipe": {"type": "Pipe", "params": {"length": "100 ft", "inner_diameter": 0.1}},
            "valve": {"type": "Valve", "params": {}},
        },
        "connections": [{"source": "pipe.fluid_out", "target": "valve.fluid_in"}],
        "inlets": {"feed": "pipe.fluid_in", "air": "pipe.air_in"},
        "outlets": {"product": "valve.fluid_out", "loss": "pipe.loss_out"},
        "bindings": {"pipe": {"heat_loss": {"column": "q", "unit": "kW"}, "velocity": "v"}},
        "param_history": {
            "pipe": [
                {"valid_from": "2020-01-01T00:00:00Z", "params": {"length": 30.48}},
                {"valid_from": "2021-01-01T00:00:00Z", "params": {"length": "200 ft"}},
            ]
        },
        "fluids": {"pipe": gm.WATER.model_dump(mode="json")},
    }
    complete = {"bindings": {}, "param_history": {}} | spec
    plant = gm.plants.from_spec(complete)
    written = plant.to_spec()
    assert written["modules"]["pipe"]["params"] == {"length": "100 ft", "inner_diameter": 0.1}
    assert written == {key: complete[key] for key in written}
    assert set(written) - set(complete) == set()
    assert gm.plants.from_spec(written).to_spec() == written


def test_a_nested_spec_and_a_group_round_trip_and_run_parameters_through():
    """A child of plant type takes dotted params; a group nests children."""
    spec = {
        "format": 2,
        "name": "DoubletHeatPlant",
        "modules": {
            "doublet": {"type": "Doublet", "params": {"esp.stage_count": 12}},
            "filters": {"type": "ModuleDict", "modules": {"hot": {"type": "Filter", "params": {}}}},
        },
        "connections": [{"source": "doublet.supply_out", "target": "filters.hot.fluid_in"}],
        "inlets": {"return_in": "doublet.return_in", "power_in": "doublet.power_in"},
        "outlets": {"product": "filters.hot.fluid_out"},
        "bindings": {},
        "param_history": {},
    }
    plant = gm.plants.from_spec(spec)
    assert plant.doublet.esp.stage_count == 12
    assert plant.to_spec() == spec


def test_an_opened_plant_round_trips_its_nested_wiring():
    """The shipped heat plant opens its doublet and still writes it as one child."""
    plant = gm.plants.library.build("DoubletHeatPlant")
    spec = plant.to_spec()
    assert spec["modules"]["doublet"] == {"type": "Doublet", "params": {}}
    assert gm.plants.from_spec(spec).to_spec() == spec


def test_params_set_since_and_validation_agree_with_the_builder():
    """``Plant.validate()`` is ``gm.plants.validate`` of its spec."""
    plant = gm.Plant("Same")
    plant.add("Pipe", "pipe", params={"length": 5.0})
    plant.connect("feed", "pipe.fluid_in")
    plant.connect("air", "pipe.air_in")
    plant.connect("pipe.fluid_out", "product")
    plant.connect("pipe.loss_out", "loss")
    found = plant.validate(on_error="record")
    assert found == gm.plants.validate(plant.to_spec(), on_error="record")
    assert {item["code"] for item in found} == {"root_plant_port"}
    with pytest.raises(gm.errors.ValidationError):
        plant.add("Pipe", "bad", params={"length": "5 bar"})


def test_a_raised_error_carries_every_problem_of_the_list_record_returns():
    """``from_dict``, ``gm.plants.validate`` and ``plant.validate`` tell one story in one try."""
    spec = {
        "format": 2,
        "name": "DoubletHeatPlant",
        "modules": {"a": {"type": "Boilr"}, "pipe": {"type": "Pipe", "params": {"length": -5.0}}},
        "connections": [],
        "inlets": {"feed": "pipe.fluid_in", "air": "pipe.air_in"},
        "outlets": {"product": "pipe.fluid_out", "loss": "pipe.loss_out"},
        "bindings": {},
        "param_history": {},
    }
    recorded = gm.plants.validate(spec, on_error="record")
    assert [item["path"] for item in recorded] == ["modules.a.type", "modules.pipe.params.length"]
    for call in (gm.plants.validate, gm.plants.from_dict, gm.plants.from_spec):
        with pytest.raises(gm.errors.ValidationError) as caught:
            call(spec)
        assert caught.value.problems == recorded and caught.value.code == recorded[0]["code"]


def test_a_valid_spec_returns_no_problems_under_both_policies():
    """Without problems nothing is raised; the list is empty."""
    plant = gm.Plant("Empty")
    assert plant.validate() == plant.validate(on_error="record") == []
    with pytest.raises(gm.errors.ValidationError, match="on_error"):
        plant.validate(on_error="ignore")


def test_plant_validate_raises_what_the_spec_function_raises():
    """A plant with a bad stated value fails its own ``validate``."""
    plant = gm.Plant("Broken")
    plant.add("Pipe", name="pipe")
    plant.set_bindings("pipe", {"velocity": "v"})
    plant.bindings["no.such.module"] = plant.bindings["pipe"]
    with pytest.raises(gm.errors.ValidationError) as caught:
        plant.validate()
    assert caught.value.problems == plant.validate(on_error="record")


def test_a_broken_module_does_not_hide_the_other_end_of_a_connection():
    """Every problem comes at once, also on a connection with one good end."""
    spec = {
        "format": 2,
        "name": "DoubletHeatPlant",
        "modules": {"a": {"type": "Boilr"}, "pipe": {"type": "Pipe"}},
        "connections": [
            {"source": "a.fluid_out", "target": "b.fluid_in"},
            {"source": "a.fluid_out", "target": "pipe.inlt"},
        ],
        "bindings": {},
        "param_history": {},
    }
    problems = gm.plants.validate(spec, on_error="record")
    assert {item["path"] for item in problems} == {
        "modules.a.type",
        "connections[0].target",
        "connections[1].target",
        "pipe.fluid_in",
        "pipe.fluid_out",
        "pipe.air_in",
        "pipe.loss_out",
    }
