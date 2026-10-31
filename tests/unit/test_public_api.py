"""Curated user API and plant ownership contracts."""

import inspect
import json
import tomllib
from pathlib import Path

import gemini as gm
from tests.fixtures.capture_public_api import SNAPSHOT, capture, fingerprint

SNAPSHOTS = {
    "0.1.0": "f19ae90f18bb5a5a85e1b1f730276c9a50fdba0d46108c4bcd56488b48178a8b",
    "0.2.0": "f6f80fb087eaedb3484507dd51eae722d6cdc667a818d807a442c8cfe1a88bdd",
}
"""Hash of the snapshot per ``gm.__version__``: a released entry never changes."""


def test_public_names_and_docs():
    """Interactive completion exposes exactly the documented, individually documented names."""
    expected = {
        "schedule",
        "simulate",
        "replay",
        "live",
        "resume",
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
    }
    assert set(dir(gm)) == expected == set(gm.__all__)
    assert all(getattr(gm, name).__doc__ for name in expected)
    assert all(getattr(gm.modules, name).__doc__ for name in gm.modules.__all__)
    assert "Doublet" in gm.plants.names()


def test_readable_tree():
    """Printing a loaded plant displays nested equipment and scalar human-unit parameters."""
    plant = gm.plants.example("DoubletHeatPlant")
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


def test_the_snapshot_changes_only_with_the_version():
    """A stored snapshot belongs to one version; changing it means raising the version."""
    stored = json.loads(SNAPSHOT.read_text())
    assert stored["version"] == gm.__version__
    assert fingerprint(stored) == SNAPSHOTS[gm.__version__]


def test_the_change_log_lists_the_version():
    """Each version has a line in the change log of the API page."""
    page = (Path(__file__).parents[2] / ".claude/docs/api.md").read_text()
    assert f"| {gm.__version__} |" in page.split("## Change log")[1]


def test_the_package_has_one_version():
    """``gm.API_VERSION`` is gone; ``gm.__version__`` is the one version."""
    assert not hasattr(gm, "API_VERSION")
    assert gm.__version__ == "0.2.0"


def test_every_economics_function_takes_the_plant_and_the_results():
    """``capex`` alone has no results; ``co2`` takes the plant too."""
    for name in ("opex", "lcoh", "lcoc", "lcts", "annualised_cost", "co2", "npv", "payback"):
        arguments = list(inspect.signature(getattr(gm.economics, name)).parameters)
        assert arguments[:2] == ["plant", "results"], name
    assert list(inspect.signature(gm.economics.capex).parameters)[0] == "plant"


def test_evaluate_stays_beside_the_run_functions():
    """A call at one point is a run at one point; ``gm.testing`` is for developers."""
    assert "evaluate" in gm.__all__ and "testing" in gm.__all__
    assert gm.testing.__all__ == ["check_module"]


def test_utils_stays_private():
    """Helpers are not part of the public API."""
    assert "utils" not in gm.__all__


def test_the_old_project_import_is_public_only_through_convert_legacy():
    """``gm.legacy`` is gone; ``gm.plants.convert_legacy`` is the one public entry."""
    assert not hasattr(gm, "legacy")
    assert "convert_legacy" in gm.plants.__all__
