"""Portable configuration and explicit GEMINI field accounting."""

import warnings
from datetime import datetime, timezone
from pathlib import Path

import pytest

from gemini.core.config.build import build_plant, load_config, plant_to_config, save_config
from gemini.core.config.gemini_loader import load_gemini
from gemini.core.config.schema import DatedParams, ModuleConfig
from gemini.core.physics.units import to_si

DATA = Path(__file__).parents[3] / "datasets/geothermal_doublet"


def test_project_roundtrip_and_accounting(tmp_path):
    """All example fields are mapped or explained and JSON preserves the full design."""
    with warnings.catch_warnings(record=True) as caught:
        config = load_gemini(DATA)
    assert not caught and not config.unmapped
    assert all(config.ignored.values())
    plant = build_plant(config)
    path = tmp_path / "plant.json"
    save_config(plant_to_config(plant), path)
    rebuilt = build_plant(load_config(path))
    assert plant.state_dict() == rebuilt.state_dict()
    assert plant.links == rebuilt.links
    assert len(plant.links) == 10
    assert plant.get_submodule("production_well_c774").params.segment == "below_esp"
    assert plant.get_submodule("production_well_c774_riser").params.segment == "above_esp"


def test_dated_params_and_units():
    """Dates select complete snapshots and data units fail closed."""
    item = ModuleConfig(
        type="filter",
        params=[
            DatedParams(valid_from="2024-02-01", params={"dp_nominal": 2}),
            DatedParams(params={"dp_nominal": 1}),
        ],
    )
    assert item.at(datetime(2024, 1, 1)).params["dp_nominal"] == 1
    assert item.at(datetime(2024, 3, 1, tzinfo=timezone.utc)).params["dp_nominal"] == 2
    assert to_si(1, "bar") == 1e5
    assert to_si(0, "barg") == 101325
    assert to_si(0, "degC") == 273.15
    assert to_si(3600, "m3/h") == 1
    with pytest.raises(ValueError, match="Unknown data unit"):
        to_si(1, "psi")
