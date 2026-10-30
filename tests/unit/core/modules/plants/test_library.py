"""Plants that ship as spec files."""

import gemini as gm
from gemini.core.modules.plants import library


def test_shipped_specs_are_registered_as_plants():
    """The registry builds a new plant for each shipped name."""
    assert {"Doublet", "DoubletHeatPlant"} <= set(gm.modules.names("plant"))
    assert gm.modules.get("Doublet") is not gm.modules.get("Doublet")
    assert library.has("Doublet") and not library.has("Nothing")


def test_every_shipped_spec_is_valid_and_round_trips():
    """A shipped file builds without problems and rewrites to itself."""
    for path in sorted(library.SPECS.glob("*.json")):
        spec = library.shipped(path.stem)
        assert library.build(path.stem).to_spec() == spec, path.name


def test_fill_adds_a_shipped_spec_to_an_empty_plant():
    """The transitional plant class builds the shipped wiring."""
    plant = gm.Plant("DoubletHeatPlant")
    library.fill(plant, "DoubletHeatPlant")
    assert list(plant.inlets()) == ["secondary_in"]
    assert list(plant.outlets()) == ["secondary_out", "gas"]
    assert list(plant.outputs(recurse=False)) == [
        "thermal_power",
        "electricity",
        "cop",
        "heat_loss",
    ]
