"""One run of a plant: what its paths read."""

import pytest

import gemini as gm
from gemini.modules.plants._utils.run import Run


def plant():
    """Return the doublet of the example plant."""
    return gm.plants.example("DoubletHeatPlant").doublet


def test_a_path_reads_a_declaration_of_the_plant():
    """What names no step is a parameter or boundary of the plant or of a child."""
    doublet = plant()
    run = Run(doublet, {})
    assert run.read("drainage_radius") == doublet.drainage_radius
    assert run.read("esp.stage_count") == doublet.esp.stage_count


def test_an_unknown_path_raises():
    """A path that names nothing says so."""
    with pytest.raises(gm.errors.ValidationError):
        Run(plant(), {}).read("nothing.at.all")
