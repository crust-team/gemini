"""End-to-end old/new bridge round trips."""

from pathlib import Path

import pytest

import gemini as gm
from examples.shared.doublet_heat.plant import DoubletHeatPlant

pytestmark = pytest.mark.e2e
ROOT = Path(__file__).parents[2]
OLD = ROOT / "examples/legacy/gemini_project_bridge/old_project"
SHARED = ROOT / "examples/shared/doublet_heat"


def test_legacy_bridge(tmp_path):
    """Convert old assets, replay, write old outputs and preserve raw project values."""
    project = gm.legacy.read_project(OLD)
    plant = gm.legacy.to_plant(project, DoubletHeatPlant())
    data = gm.legacy.to_dataset(project, gm.legacy.read_csv(OLD / "doublet_2024_old.csv"))
    assert gm.legacy.check_wiring(plant, project) == []
    plant.save(tmp_path / "plant.json")
    frame = data.to_frame()
    frame.index.name = "time"
    frame.reset_index().to_csv(
        tmp_path / "doublet_2024_15min.csv", index=False, float_format="%.17g"
    )
    assert (tmp_path / "plant.json").read_bytes() == (SHARED / "plant.json").read_bytes()
    assert (tmp_path / "doublet_2024_15min.csv").read_bytes() == (
        SHARED / "doublet_2024_15min.csv"
    ).read_bytes()
    results = gm.Engine().replay(plant, data.window(end=data.start))
    old_results = gm.legacy.results_to_frame(results, project)
    gm.legacy.write_csv(old_results, tmp_path / "results.csv")
    assert len(gm.legacy.read_csv(tmp_path / "results.csv")) == 1
    gm.legacy.write_project(gm.legacy.from_plant(plant, project), tmp_path / "project")
    reread = gm.legacy.read_project(tmp_path / "project")
    assert reread.params == project.params
