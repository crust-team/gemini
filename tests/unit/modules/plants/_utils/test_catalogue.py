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
    "ATESPlant": "7ae7cf36bd0d34f7039c2881cffb107b769d0ad4f12f53b66359fe1053842210",
    "BoilerChpPlant": "a9213b64867d13df1d31e86a2e60eda6332b434d532ca822e7a2c3b086dcd7a3",
    "CoolingSubstation": "e332a3aae55afa8e6e7e947af66dead26b410d88644c3b23bfed1468001e4a5c",
    "DistrictEnergyPlant": "64940b883163bc81e59fa8ffa4879dbc6cb3d737786f3e200a1f76787a390e76",
    "DistrictNetwork": "3475084a865a4a441eb0743ab9ae81356d0412ab69144c6a0b0a02e31cd2a9e6",
    "Doublet": "7e38703b880e458aef5d3957bc7cc7d51ffc8c9b067d8da0b6c3568dd88249e2",
    "DoubletHeatPlant": "8ef986a72459b8b04d5cd1f6534644c3c8584428ab1e1b2368d2c7c21bad22ee",
    "HackathonPlant": "7c08b843eeed473c393f7ba429ab1e5f634490f52fa27fd64d20db175b2163b4",
    "HeatingSubstation": "f1306278048f262a2b088d3d895882f802aff702f69358c6615de849fc4bddf5",
    "MultiWellPlant": "30c96f8dec0a190ffb5333e40465dd2437c43fae1952736ee8356344252d4251",
    "NodalDoublet": "012940e8e779020cd6212111cf8b0fafeae60bd517979cfe1632358b66a918f7",
    "ParallelExchangerPlant": "d8b21e47275c3b8d0c0d88241c05a1fcd95951dc5cec38e3775ad31ef43eea8b",
    "HeatingPlant": "b0406f5198d2f66c6c4c8e16214a4e673d48dd3a401d6f645c1ed29c5112cf9f",
    "HeatingCoolingPlant": ("ef6272c8273566a9d1e5405b7f44a70f9b73476413d1d406e553fb5c3a486409"),
    "HeatingFullCoolingPlant": ("b9f166125c8053b4382c3c836b51027d63800dad6ab517894f7bbb84206fa49f"),
    "HeatingAbsorptionCoolingPlant": (
        "f09515814b073275ff3446e399be7470eea59f02f8e4c357fc71d4bb916aa47a"
    ),
    "HeatingHeatPumpCoolingPlant": (
        "b552a6f19cee4e70eb7656576deeb14eda58cf2a34d11917e8071766b1f58080"
    ),
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
    spec = catalogue.example(name).to_dict()
    assert gm.plants.validate(spec) == []
    assert gm.plants.from_dict(spec).to_dict() == spec


@pytest.mark.parametrize("name", catalogue.names())
def test_every_example_equals_the_plant_of_its_former_file(name):
    """``get`` and the values of ``inputs/plants/`` give the structure and the values pinned."""
    spec = catalogue.example(name).to_dict(structure=True)
    if name == "Doublet":
        del spec["outputs"]
    text = json.dumps(spec, sort_keys=True)
    assert hashlib.sha256(text.encode()).hexdigest() == FORMER_EXAMPLES[name]


def test_the_doublet_examples_carry_the_shared_doublet_heat_values():
    """The doublet is the ``doublet`` child of the doublet heat plant."""
    shared = catalogue.example("DoubletHeatPlant").to_dict(structure=True)
    doublet = catalogue.example("Doublet")
    expected = shared["modules"]["doublet"]["params"]
    assert {
        f"{path}.{name}": value
        for path, entry in doublet.to_dict(structure=True)["modules"].items()
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
    assert empty._connections == filled._connections
    assert filled.d0.reservoir.temperature == filled.d1.reservoir.temperature
    assert filled.heat_users.fluid == gm.WATER


def test_a_registered_plant_without_values_names_itself(monkeypatch):
    """Only a plant with no sourced values raises, and the message names it."""
    entry = registry._Entry("plants", module=type("Unsourced", (gm.Plant,), {}))
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


def test_names_lists_the_plants_of_a_purpose():
    """``category`` is what a plant serves; a building block serves nothing by itself."""
    assert catalogue.names("heating") == ["HeatingPlant"]
    assert "HeatingCoolingPlant" in catalogue.names("both")
    assert "Doublet" not in catalogue.names("both") + catalogue.names("heating")
    with raises(gm.errors.ValidationError, "unknown_name"):
        catalogue.names("steam")
