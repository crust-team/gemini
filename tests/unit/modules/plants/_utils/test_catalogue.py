"""The plant catalogue: names and new plants."""

import hashlib
import json

import pytest

import gemini as gm
from gemini.modules._utils import registry
from gemini.modules.plants._utils import catalogue
from gemini.utils import paths
from tests.fixtures.errors import raises

FORMER_EXAMPLES = {
    "ATESPlant": "29d157ac8c1b6006d60bacfc6fb821bb7cbc0c21b058cb8e69642c02f24873da",
    "BoilerChpPlant": "335077245c94a8df846af18376abf4f275732ea5fb4e3555a797720c848edf8f",
    "CoolingSubstation": "e724b534942334e8216d459a957dbd42f43f9df34785cc1fabc995abc59d9d16",
    "DistrictEnergyPlant": "1df6cb451b7b87affc28199318182fd64dc8b49bbf6b8626a15cbd6140f32c90",
    "DistrictNetwork": "cc5a52fa7e7372f532f8e2aacbb6f14f716737735e0ba1418c90ab3e2e3f91d5",
    "Doublet": "7e38703b880e458aef5d3957bc7cc7d51ffc8c9b067d8da0b6c3568dd88249e2",
    "DoubletHeatPlant": "a83a084462d47570c0b880efa2dd0a932500e07af8e306edbab3b5203d18a670",
    "HackathonPlant": "6da42c88a06d8bc97c03b556097cf0e86396d1dc66c8e5bc74638cb987c570b7",
    "HeatingSubstation": "5e0e18c308feb515bb95398ab341f00e471346b7f79ec78fafc541d385ec832d",
    "MultiWellPlant": "8946346c436b21e7c3c71f9ca019db963267c67ebad052599100017ade1ee83d",
    "NodalDoublet": "612091520ef3c6d1b1b242f746a5277c85854f7a013aee4a21c2dcaa2d9ae674",
    "ParallelExchangerPlant": "47f565bedb445d011e61e8f3231435886e3ab12a48adb87030d3ed97b0c8d61c",
}
"""Hash of ``to_dict()`` of the plant built from each whole example file these values replaced.

NOTE(refactor): ``HackathonPlant`` is hashed with its 24 stated values in SI, because ``set_params``
stores SI where the former file kept text such as ``"2500 m"``; its ``state_dict`` was equal, the
derived child values included. ``Doublet`` is hashed without ``outputs``, which its structure file
has and its former example file lacked.
"""


def test_names_are_the_registered_plants():
    """Spec plants and the special cases are listed, sorted, and nothing else."""
    assert catalogue.names() == gm.modules.names("plants")
    assert {"Doublet", "DoubletHeatPlant", "MultiWellPlant", "DistrictNetwork"} <= set(
        catalogue.names()
    )
    assert {"HeatingSubstation", "CoolingSubstation", "ATESPlant"} <= set(catalogue.names())
    assert {"NodalDoublet", "ParallelExchangerPlant", "BoilerChpPlant"} <= set(catalogue.names())
    assert {"DistrictEnergyPlant", "HackathonPlant"} <= set(catalogue.names())
    assert "ESP" not in catalogue.names()


def test_get_returns_a_new_plant_without_values():
    """A spec plant is a Plant, a special case an instance of its class; each call is new."""
    first, second = catalogue.get("Doublet"), catalogue.get("Doublet")
    assert isinstance(first, gm.Plant) and first is not second
    assert isinstance(catalogue.get("HeatingSubstation"), gm.modules.HeatingSubstation)
    assert first.name == "Doublet"


def test_get_refuses_unknown_names_and_modules_that_are_not_plants():
    """An unknown name has close matches; a pump is not a plant."""
    with raises(gm.errors.ValidationError, "unknown_name") as unknown:
        catalogue.get("DubletHeatPlant")
    assert "DoubletHeatPlant" in unknown.value.suggestions
    with raises(gm.errors.ValidationError, "unknown_name"):
        catalogue.get("ESP")


@pytest.mark.parametrize("name", catalogue.names())
def test_every_spec_plant_and_special_case_has_an_example_that_round_trips(name):
    """An example builds, has no problems and writes the spec it was read from."""
    spec = catalogue.example(name).to_spec()
    assert gm.plants.validate(spec) == []
    assert gm.plants.from_spec(spec).to_spec() == spec


@pytest.mark.parametrize("name", catalogue.names())
def test_every_example_equals_the_plant_of_its_former_file(name):
    """``get`` and the values of ``inputs/plants/`` give the plant the whole file gave."""
    spec = catalogue.example(name).to_dict()
    if name == "Doublet":
        del spec["outputs"]
    text = json.dumps(spec, sort_keys=True)
    assert hashlib.sha256(text.encode()).hexdigest() == FORMER_EXAMPLES[name]


def test_the_doublet_examples_carry_the_shared_doublet_heat_values():
    """The doublet is the ``doublet`` child of the doublet heat plant."""
    shared = catalogue.example("DoubletHeatPlant").to_spec()
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


def test_a_state_dictionary_fills_a_plant_without_values():
    """A plant from ``get`` has no values and takes those of an example; groups stay groups."""
    example = catalogue.example("DoubletHeatPlant")
    assert isinstance(example.filters, gm.modules.ModuleDict)
    fresh = catalogue.get("DoubletHeatPlant")
    assert not fresh.is_initialized
    fresh.load_state_dict(example.state_dict())
    assert fresh.is_initialized


def test_the_hackathon_plant_has_its_values_only_in_the_example():
    """The registered spec is the wiring, and the example fills every module of it."""
    empty, filled = catalogue.get("HackathonPlant"), catalogue.example("HackathonPlant")
    assert not empty.is_initialized and filled.is_initialized
    assert empty.to_spec()["connections"] == filled.to_spec()["connections"]
    assert filled.d0.reservoir.temperature == filled.d1.reservoir.temperature
    assert filled.heat_users.fluid == gm.WATER


def test_a_registered_plant_without_values_names_itself(monkeypatch):
    """Only a plant with no sourced values raises, and the message names it."""
    entry = registry._Entry("plants", build=lambda: gm.Plant("Unsourced"))
    monkeypatch.setitem(registry._entries, "Unsourced", entry)
    with pytest.raises(gm.errors.NotImplementedYet, match="Unsourced"):
        catalogue.example("Unsourced")


def test_an_example_needs_a_source_checkout(tmp_path, monkeypatch):
    """Without ``inputs/`` the error names the file; the plant itself stays available."""
    monkeypatch.setattr(paths, "INPUTS", tmp_path / "absent")
    with raises(gm.errors.RunError, "inputs_missing") as missing:
        catalogue.example("Doublet")
    assert "plants/Doublet.json" in str(missing.value)
    assert catalogue.get("Doublet").name == "Doublet"


def test_example_refuses_unknown_names_with_close_matches():
    """A misspelt plant name has suggestions."""
    with raises(gm.errors.ValidationError, "unknown_name") as unknown:
        catalogue.example("Doublt")
    assert "Doublet" in unknown.value.suggestions


def test_templates_list_name_title_description_and_purpose():
    """The catalogue lists the templates the way the backend route returns them."""
    rows = catalogue.templates()
    assert {row["name"] for row in rows} >= {"multi_well", "district_network"}
    assert all(set(row) == {"name", "title", "description", "purpose"} for row in rows)
