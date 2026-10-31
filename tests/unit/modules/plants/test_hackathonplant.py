"""The class of the HackathonPlant: its example validates and rebuilds."""

import gemini as gm


def test_the_example_is_complete_and_valid():
    """Every port is connected and every parameter has a value."""
    plant = gm.plants.example("HackathonPlant")
    assert plant.is_initialized
    assert plant.validate(on_error="record") == []
