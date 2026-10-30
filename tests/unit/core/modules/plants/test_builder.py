"""Plants built from data."""

import gemini as gm


def test_a_plant_is_a_module_in_the_plant_category():
    """A built plant is a normal composite."""
    assert isinstance(gm.Plant("doublet"), gm.modules.Module)
    assert gm.Plant.category == "plant"
