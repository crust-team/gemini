"""The plant catalogue: names and new plants."""

import pytest

import gemini as gm
from gemini.core.modules import registry
from gemini.core.modules.plants import catalogue
from gemini.utils.files import read_json
from tests.fixtures import SHARED


def test_names_are_the_registered_plants():
    """Spec plants and the special cases are listed, sorted, and nothing else."""
    assert catalogue.names() == gm.modules.names("plant")
    assert {"Doublet", "DoubletHeatPlant", "MultiWellPlant", "DistrictNetwork"} <= set(
        catalogue.names()
    )
    assert {"HeatingSubstation", "CoolingSubstation", "ATESPlant"} <= set(catalogue.names())
    assert "ESP" not in catalogue.names()


def test_get_returns_a_new_plant_without_values():
    """A spec plant is a Plant, a special case an instance of its class; each call is new."""
    first, second = catalogue.get("Doublet"), catalogue.get("Doublet")
    assert isinstance(first, gm.Plant) and first is not second
    assert isinstance(catalogue.get("HeatingSubstation"), gm.modules.HeatingSubstation)
    assert first.name == "Doublet"


def test_get_refuses_unknown_names_and_modules_that_are_not_plants():
    """An unknown name has close matches; a pump is not a plant."""
    with pytest.raises(gm.errors.UnknownNameError) as unknown:
        catalogue.get("DubletHeatPlant")
    assert "DoubletHeatPlant" in unknown.value.suggestions
    with pytest.raises(gm.errors.UnknownNameError):
        catalogue.get("ESP")


@pytest.mark.parametrize("name", catalogue.names())
def test_every_spec_plant_and_special_case_has_an_example_that_round_trips(name):
    """An example builds, has no problems and writes the spec it was read from."""
    spec = catalogue.example(name).to_spec()
    assert gm.plants.validate(spec) == []
    assert gm.plants.from_spec(spec).to_spec() == spec


def test_the_doublet_examples_carry_the_shared_doublet_heat_values():
    """The package copy equals the shared plant file; the doublet is its ``doublet`` child."""
    shared = read_json(SHARED / "plant.json")
    assert catalogue.example("DoubletHeatPlant").to_spec() == shared
    doublet = catalogue.example("Doublet")
    expected = shared["modules"]["doublet"]["params"]
    assert {
        f"{path}.{name}": value
        for path, entry in doublet.to_spec()["modules"].items()
        for name, value in entry["params"].items()
    } == expected


def test_the_other_examples_carry_the_values_of_their_tests(plants):
    """The substations and the network are filled as the unit tests of their folder fill them."""
    heating = plants["heating_substation"](catalogue.get("HeatingSubstation"))
    assert catalogue.example("HeatingSubstation").state_dict() == heating.state_dict()
    cooling = plants["cooling_substation"](catalogue.get("CoolingSubstation"))
    assert catalogue.example("CoolingSubstation").state_dict() == cooling.state_dict()
    network = plants["network"](catalogue.get("DistrictNetwork"), plants["heating_substation"])
    assert catalogue.example("DistrictNetwork").state_dict() == network.state_dict()


def test_a_registered_plant_without_values_names_itself(monkeypatch):
    """Only a plant with no sourced values raises, and the message names it."""
    entry = registry._Entry("plant", build=lambda: gm.Plant("Unsourced"))
    monkeypatch.setitem(registry._entries, "Unsourced", entry)
    with pytest.raises(gm.errors.NotImplementedYet, match="Unsourced"):
        catalogue.example("Unsourced")


def test_example_refuses_unknown_names_with_close_matches():
    """A misspelt plant name has suggestions."""
    with pytest.raises(gm.errors.UnknownNameError) as unknown:
        catalogue.example("Doublt")
    assert "Doublet" in unknown.value.suggestions


def test_templates_list_name_title_description_and_purpose():
    """The catalogue lists the templates the way the backend route returns them."""
    rows = catalogue.templates()
    assert {row["name"] for row in rows} >= {"MultiWellPlant", "DistrictNetwork"}
    assert all(set(row) == {"name", "title", "description", "purpose"} for row in rows)
