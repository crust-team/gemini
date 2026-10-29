"""Curated user API and plant ownership contracts."""

import tomllib
from pathlib import Path

import gemini as gm


def test_public_names_and_docs():
    """Interactive completion exposes exactly the documented, individually documented names."""
    expected = {
        "Engine",
        "Clock",
        "Dataset",
        "Profile",
        "Stream",
        "Ports",
        "Fluid",
        "BRINE",
        "WATER",
        "Quantity",
        "runtime",
        "units",
        "legacy",
        "modules",
        "plants",
        "optim",
        "errors",
        "no_outputs",
        "__version__",
    }
    assert set(dir(gm)) == expected == set(gm.__all__)
    assert all(getattr(gm, name).__doc__ for name in expected)
    assert all(getattr(gm.modules, name).__doc__ for name in gm.modules.__all__)
    assert gm.plants.Doublet


def test_readable_tree():
    """Printing a loaded plant displays nested equipment and scalar human-unit parameters."""
    from examples.shared.doublet_heat.plant import DoubletHeatPlant

    plant = DoubletHeatPlant.load(
        Path(__file__).parents[2] / "examples/shared/doublet_heat/plant.json"
    )
    with gm.runtime.settings(display_units="field"):
        rendered = repr(plant)
    assert "DoubletHeatPlant(" in rendered and "(doublet): Doublet(" in rendered
    assert "ESP(" in rendered and "bar" in rendered and "°C" in rendered


def test_version_matches_the_package_metadata():
    """The version literal in ``gemini/__init__.py`` is the one in ``pyproject.toml``."""
    project = tomllib.loads((Path(__file__).parents[2] / "pyproject.toml").read_text())
    assert gm.__version__ == project["tool"]["poetry"]["version"]
