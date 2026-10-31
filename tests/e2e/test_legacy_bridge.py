"""End-to-end old/new bridge round trips."""

from pathlib import Path

import pytest

import gemini as gm
from gemini.utils import legacy

pytestmark = pytest.mark.e2e
ROOT = Path(__file__).parents[2]
OLD = ROOT / "datasets/legacy_project"
SHARED = ROOT / "datasets/doublet_heat"


def test_legacy_bridge(tmp_path):
    """Convert old assets, replay, write old outputs and preserve raw project values."""
    project = legacy.read_project(OLD)
    plant = legacy.to_plant(project, gm.plants.get("DoubletHeatPlant"))
    data = legacy.to_dataset(project, legacy.read_csv(OLD / "doublet_2024_old.csv"))
    assert legacy.check_wiring(plant, project) == []
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
    results = gm.replay(plant, data.window(end=data.start))
    old_results = legacy.results_to_frame(results, project)
    legacy.write_csv(old_results, tmp_path / "results.csv")
    assert len(legacy.read_csv(tmp_path / "results.csv")) == 1
    converted = legacy.from_plant(plant, project)
    legacy.write_project(converted, tmp_path / "project")
    reread = legacy.read_project(tmp_path / "project")
    assert reread.params == project.params
    plant.heat_exchanger.update_params(thermal_conductance=123456.0)
    updated = legacy.from_plant(plant, project)
    legacy.write_project(updated, tmp_path / "updated")
    reread = legacy.read_project(tmp_path / "updated")
    hx_id = next(
        node_id for node_id, node in project.nodes.items() if node.type == "heat_exchanger"
    )
    assert reread.params[hx_id]["heat_transfer_coeff"].values == [123456.0]
