"""The class of the HeatingCoolingPlant: its example validates and rebuilds."""

import gemini as gm


def test_the_example_is_complete_and_rebuilds():
    """Every port is connected, and the plant dict gives the same plant."""
    plant = gm.plants.example("HeatingCoolingPlant")
    assert plant.is_initialized
    assert plant.validate(on_error="record") == []
    assert gm.plants.from_dict(plant.to_dict()).to_dict() == plant.to_dict()
