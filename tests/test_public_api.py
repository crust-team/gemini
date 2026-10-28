"""Curated user API and plant ownership contracts."""

import gemini as gm


def test_public_names_and_docs():
    """Interactive completion exposes exactly the documented, individually documented names."""
    expected = {
        "Engine",
        "Clock",
        "Dataset",
        "Profile",
        "Stream",
        "Fluid",
        "BRINE",
        "WATER",
        "load_plant",
        "modules",
        "plants",
        "optim",
        "__version__",
    }
    assert set(dir(gm)) == expected == set(gm.__all__)
    assert all(getattr(gm, name).__doc__ for name in expected)
    assert all(getattr(gm.modules, name).__doc__ for name in gm.modules.__all__)
    assert gm.plants.Doublet and gm.plants.GeothermalExamplePlant


def test_readable_tree():
    """Printing a loaded plant displays nested equipment and scalar human-unit parameters."""
    from pathlib import Path

    plant = gm.load_plant(Path(__file__).parents[1] / "datasets/geothermal_doublet")
    rendered = repr(plant)
    assert "GeothermalExamplePlant(" in rendered and "(doublet): Doublet(" in rendered
    assert "ESP(" in rendered and "bar" in rendered and "°C" in rendered
