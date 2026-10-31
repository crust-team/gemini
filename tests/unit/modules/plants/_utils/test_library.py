"""Plants that ship as spec files."""

import gemini as gm
from gemini.modules.plants._utils import library
from gemini.utils.paths import ASSET_PLANTS


def test_has_names_a_shipped_file():
    """Only a file that ships counts."""
    assert library.has("Doublet") and not library.has("Nothing")


def test_every_shipped_spec_is_valid_and_round_trips():
    """A shipped file builds without problems and rewrites to itself."""
    for path in sorted(ASSET_PLANTS.glob("*.json")):
        spec = library.shipped(path.stem)
        assert library.build(path.stem).to_spec() == spec, path.name


def test_fill_adds_a_shipped_spec_to_an_empty_plant():
    """The transitional plant class builds the shipped wiring."""
    plant = gm.Plant("DoubletHeatPlant")
    library.fill(plant, "DoubletHeatPlant")
    assert list(plant.inlets()) == ["return_in", "power_in"]
    assert list(plant.outlets()) == ["supply_out", "gas_out"]
    assert list(plant.outputs(recurse=False)) == [
        "thermal_power",
    ]
