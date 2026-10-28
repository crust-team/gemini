"""Configuration-boundary tests using raw timestamped GEMINI property blocks."""

import json
from pathlib import Path

import pytest

from gemini.core.config import param_mapping as mapping
from gemini.core.engine import registry

DATA = Path(__file__).parents[3] / "datasets/geothermal_doublet"


@pytest.mark.parametrize("path", sorted(DATA.glob("*.param")), ids=lambda p: p.name)
def test_all_example_property_blocks(path):
    """Every example property block, including both filters and both reservoirs, validates."""
    source = json.loads(path.read_text())
    p = source["parameters"]["property"]
    kind = source["type"].replace("_", "")
    if kind == "reservoir":
        production = "c1b5" in path.name
        well = "production_well_c774.param" if production else "injection_well_a06b.param"
        role = "production" if production else "injection"
        params = mapping.reservoir_params_from_gemini(p, mapping.read_property(DATA / well), role)
        kind = role + "_reservoir"
    else:
        params = getattr(mapping, kind + "_params_from_gemini")(p)
    registry.create(kind, params)


def test_multiple_parameter_timestamps_and_csv_trajectory():
    """Keep scalar snapshots intact and resolve trajectory filenames at the file boundary."""
    raw = json.loads((DATA / "esp_1ee3.param").read_text())["parameters"]["property"]
    repeated = {k: v * 2 for k, v in raw.items()}
    assert mapping.esp_params_from_gemini(repeated) == mapping.esp_params_from_gemini(
        mapping.snapshot(repeated, 1)
    )
    p = mapping.read_property(DATA / "production_well_c774.param")
    p["productionwell_trajectory_table"] = []
    p["productionwell_trajectory_file"] = "well_trajectory.csv"
    mapped = mapping.productionwell_params_from_gemini(p, base_path=DATA)
    assert mapped["path"].total_length == 2800
