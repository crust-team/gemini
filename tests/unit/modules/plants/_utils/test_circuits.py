"""Where a stream goes through a plant."""

import gemini as gm
from gemini.modules.grids import CoolingGrid, HeatingGrid
from gemini.modules.heating import HeatPump
from gemini.modules.piping import Mixer, Splitter
from gemini.modules.plants._utils.circuits import outlets_after


def test_an_inlet_goes_on_through_the_outlet_of_its_role():
    """The two sides of a heat pump are two circuits."""
    assert outlets_after(HeatPump(), "sink_in") == ["sink_out"]
    assert outlets_after(HeatPump(), "source_in") == ["source_out"]


def test_a_splitter_and_a_mixer_keep_the_circuit():
    """A branch is the common circuit."""
    assert outlets_after(Splitter(), "fluid_in") == ["branch1_out", "branch2_out"]
    assert outlets_after(Mixer(), "branch2_in") == ["fluid_out"]


def test_a_grid_ends_the_circuit():
    """What the users send back is not what the unit feeds."""
    assert outlets_after(HeatingGrid(), "supply_in") == []
    assert outlets_after(CoolingGrid(), "supply_in") == []


def test_feeds_follows_the_circuit_to_the_grid():
    """Through the boiler and the pipe, nearest first, and no further than the users."""
    plant = gm.plants.get("HeatingHeatPumpCoolingPlant")
    assert plant.feeds("heat_exchanger.cold_out")[-2:] == [
        "heating_supply_pipe",
        "heating_consumer",
    ]
    assert plant.feeds("compression_chiller.source_out") == [
        "cooling_supply_pipe",
        "cooling_consumer",
    ]


def test_feeds_of_an_outlet_that_leaves_the_plant_is_empty():
    """A plant port is the end of what this plant knows."""
    assert gm.plants.get("Doublet").feeds("riser.wellhead_out") == []
