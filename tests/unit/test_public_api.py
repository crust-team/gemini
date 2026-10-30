"""Curated user API and plant ownership contracts."""

import json
import tomllib
from pathlib import Path

import gemini as gm
from tests.fixtures.capture_public_api import SNAPSHOT, capture, fingerprint

SNAPSHOTS = {
    1: "7d24bb659c94ff3f5717c4eb116a7c44ca2eb77972f96e6515a52350c28a07b0",
    2: "91dce79b8d07942960e637da063bbbac465426e883ba15cc172c9f76b6ccc15d",
    3: "1c47ff0cb57d8ef77cc41816ec42a140a304965686a577c82b2af664c8817cc9",
}
"""Hash of the snapshot per ``API_VERSION``: an entry never changes, a new version adds one."""


def test_public_names_and_docs():
    """Interactive completion exposes exactly the documented, individually documented names."""
    expected = {
        "Engine",
        "Plant",
        "Results",
        "evaluate",
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
        "streams",
        "modules",
        "plants",
        "profiles",
        "analysis",
        "economics",
        "kpi",
        "checks",
        "testing",
        "optim",
        "errors",
        "no_outputs",
        "__version__",
        "API_VERSION",
    }
    assert set(dir(gm)) == expected == set(gm.__all__)
    assert all(getattr(gm, name).__doc__ for name in expected)
    assert all(getattr(gm.modules, name).__doc__ for name in gm.modules.__all__)
    assert "Doublet" in gm.plants.names()


def test_readable_tree():
    """Printing a loaded plant displays nested equipment and scalar human-unit parameters."""
    plant = gm.Plant.load(Path(__file__).parents[2] / "examples/shared/doublet_heat/plant.json")
    with gm.runtime.settings(display_units="field"):
        rendered = repr(plant)
    assert "DoubletHeatPlant(" in rendered and "(doublet): Doublet(" in rendered
    assert "ESP(" in rendered and "bar" in rendered and "°C" in rendered


def test_version_matches_the_package_metadata():
    """The version literal in ``gemini/__init__.py`` is the one in ``pyproject.toml``."""
    project = tomllib.loads((Path(__file__).parents[2] / "pyproject.toml").read_text())
    assert gm.__version__ == project["project"]["version"]


def test_the_public_api_equals_the_stored_snapshot():
    """Every name, its parameter names and the schema files are as frozen."""
    assert capture() == json.loads(SNAPSHOT.read_text())


def test_the_snapshot_changes_only_with_the_api_version():
    """A stored snapshot belongs to one ``API_VERSION``; changing it means raising the version."""
    stored = json.loads(SNAPSHOT.read_text())
    assert stored["api_version"] == gm.API_VERSION
    assert fingerprint(stored) == SNAPSHOTS[gm.API_VERSION]


def test_the_change_log_lists_the_api_version():
    """Each version has a line in the change log of the API page."""
    page = (Path(__file__).parents[2] / ".claude/docs/api.md").read_text()
    assert f"| {gm.API_VERSION} |" in page.split("## Change log")[1]


def test_utils_stays_private():
    """Helpers are not part of the public API."""
    assert "utils" not in gm.__all__


def test_the_old_project_import_is_public_only_through_convert_legacy():
    """``gm.legacy`` is gone; ``gm.plants.convert_legacy`` is the one public entry."""
    assert not hasattr(gm, "legacy")
    assert "convert_legacy" in gm.plants.__all__
