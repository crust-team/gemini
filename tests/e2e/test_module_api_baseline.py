"""Compare the refactored API with the immutable phase-0 result fixtures."""

import json
from pathlib import Path
from time import perf_counter

import numpy as np
import pandas as pd
import pytest

import gemini as gm
from examples.shared.doublet_heat.plant import DoubletHeatPlant

pytestmark = pytest.mark.e2e
ROOT = Path(__file__).parents[2]
SHARED = ROOT / "examples/shared/doublet_heat"
BASELINE = ROOT / "tests/fixtures/module_api_baseline"
PATH_RENAMES = {"filter_hot": "filters.hot", "filter_return": "filters.cold"}
FIELD_RENAMES = {
    "energy_port_electricity": "electricity",
    "energy_port_fuel": "fuel",
    "energy_port_heat_loss": "heat_loss",
}
TYPE_RENAMES = {
    "doublet_heat": "doublet_heat_plant",
    "heatexchanger": "heat_exchanger",
    "injectionpump": "injection_pump",
    "injectionwell": "injection_well",
    "productionwell": "production_well",
}


def _baseline_frame(name):
    return (
        pd.read_csv(
            BASELINE / name,
            header=[0, 1],
            index_col=0,
            parse_dates=True,
        )
        .rename(columns=PATH_RENAMES, level=0)
        .rename(columns=FIELD_RENAMES, level=1)
    )


def _assert_values_identical(actual, expected):
    actual = actual.reindex(columns=expected.columns)
    assert actual.index.equals(expected.index)
    assert actual.columns.equals(expected.columns)
    for column in expected:
        left, right = actual[column], expected[column]
        if pd.api.types.is_numeric_dtype(left) and pd.api.types.is_numeric_dtype(right):
            # CSV fixture round-trips can differ by one binary64 ULP.
            np.testing.assert_allclose(
                left.to_numpy(), right.to_numpy(), rtol=2e-15, atol=1e-12, equal_nan=True
            )
        else:
            pd.testing.assert_series_equal(
                left.fillna("<missing>").map(str),
                right.fillna("<missing>").map(str),
                check_names=False,
                check_dtype=False,
            )


def test_state_and_full_results_match_phase_zero():
    """State, replay and simulation remain numerically identical after documented renames."""
    plant = DoubletHeatPlant.load(SHARED / "plant.json")
    old_state = json.loads((BASELINE / "state_dict.json").read_text())
    new_state = plant.state_dict()
    for old_path, old in old_state.items():
        new = new_state[PATH_RENAMES.get(old_path, old_path)]
        assert TYPE_RENAMES.get(old["type"], old["type"]) == new["type"]
        old_params = dict(old["params"])
        old_params.pop("coefficient_precision", None)
        if "path" in old_params:
            old_params["pipe_path"] = old_params.pop("path")
        assert old_params == new["params"]
        assert old["fluid"] == new["fluid"]

    frame = pd.read_csv(SHARED / "doublet_2024_15min.csv", parse_dates=["time"])
    data = gm.Dataset.from_frame(frame, time_column="time")
    started = perf_counter()
    replay = gm.Engine().replay(plant, data).to_frame()
    elapsed = perf_counter() - started
    assert elapsed < 60
    _assert_values_identical(replay, _baseline_frame("replay.csv.gz"))

    clock = gm.Clock.days(2027, 1, 1, days=1)
    profiles = {
        "doublet.reservoir.m_dot": gm.Profile.constant(150, unit="m3/h", clock=clock),
        "doublet.esp.frequency": gm.Profile.constant(55, unit="Hz", clock=clock),
        "injection_pump.pressure_setpoint": gm.Profile.constant(51.5, unit="bar", clock=clock),
    }
    simulation = (
        gm.Engine().simulate(plant, gm.Dataset.from_profiles(profiles), clock=clock).to_frame()
    )
    _assert_values_identical(simulation, _baseline_frame("simulate.csv.gz"))
