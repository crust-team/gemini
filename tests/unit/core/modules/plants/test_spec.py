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
        "name": "Units",
        "modules": {
            "pipe": {"type": "Pipe", "params": {"length": "100 ft", "inner_diameter": 0.1}},
            "valve": {"type": "Valve", "params": {}},
        },
        "connections": [{"source": "pipe.outlet", "target": "valve.inlet"}],
        "inlets": {"feed": "pipe.inlet"},
        "bindings": {"pipe": {"measured": {"heat_loss": {"column": "q", "unit": "kW"}}}},
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
        "name": "Nested",
        "modules": {
            "doublet": {"type": "Doublet", "params": {"esp.no_stages": 12}},
            "filters": {"type": "ModuleDict", "modules": {"hot": {"type": "Filter", "params": {}}}},
        },
        "connections": [{"source": "doublet.supply_out", "target": "filters.hot.inlet"}],
        "bindings": {},
        "param_history": {},
    }
    plant = gm.plants.from_spec(spec)
    assert plant.doublet.esp.no_stages == 12
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
    plant.add("Pipe", "pipe", length=5.0)
    assert plant.validate() == gm.plants.validate(plant.to_spec()) == []
    with pytest.raises(gm.errors.ValidationError):
        plant.add("Pipe", "bad", length="5 bar")
