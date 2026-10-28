"""Shared replay/live/scenario execution, missing data and calibration behaviour."""

import json
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from gemini.core.config.build import build_plant
from gemini.core.config.gemini_loader import load_gemini
from gemini.core.config.schema import DatedParams
from gemini.core.data.connector.csv_driver import CSVDriver
from gemini.core.data.timeseries import CSVTimeSeries
from gemini.core.engine.events import EventLog
from gemini.core.modes import history, live, scenario, twin
from gemini.core.types import Profile

DATA = Path(__file__).parents[3] / "datasets/geothermal_doublet"


@pytest.fixture
def setup():
    """Load a fresh design and a short measured window."""
    config = load_gemini(DATA)
    return (
        config,
        build_plant(config),
        CSVTimeSeries(DATA / "geothermal_example_dataset.csv").frame.iloc[:12],
    )


def test_replay_missing_data_events_and_export(setup, tmp_path):
    """Missing data skips only its owning twin; hooks and exports retain structured values."""
    config, plant, data = setup
    data.loc[data.index[0], "ESP_Pin"] = np.nan
    events = EventLog().attach(plant)
    result = history.replay(plant, config, data)
    frame = result.to_frame()
    assert len(frame) == 12 and isinstance(frame.columns, pd.MultiIndex)
    assert frame["doublet.esp", "head"].notna().sum() == 11
    assert frame["filter_hot", "pressure_drop"].notna().sum() == 12
    assert result.skip_counts == {"doublet.esp": {"ESP_Pin": 1}}
    assert events.events and all(e["duration_ms"] >= 0 for e in events.events)
    assert all(e["outputs"] for e in events.events)
    events.detach()
    count = len(events.events)
    twin.evaluate(plant, data.iloc[1], data.index[1])
    assert len(events.events) == count
    result.save_csv(tmp_path / "results.csv")
    pytest.importorskip("pyarrow")
    result.save_parquet(tmp_path / "results.parquet")
    assert len(pd.read_parquet(tmp_path / "results.parquet")) == 12
    disk = EventLog(tmp_path / "events.jsonl")
    disk.log("prompt", text="trace fixture")
    assert json.loads((tmp_path / "events.jsonl").read_text())["kind"] == "prompt"


def test_live_csv_scenario_and_dates(setup):
    """Existing CSV connector serves live windows; scenarios traverse every child for 24 hours."""
    config, plant, data = setup
    driver = CSVDriver()
    driver.update_parameters({"url": str(DATA / "geothermal_example_dataset.csv")})
    driver.connect()
    assert len(live.run_latest(plant, config, driver, 3)) == 3
    controls, streams = twin.scenario_inputs(plant, data.iloc[0])
    profile = Profile.constant(
        "production", "mass_flow", "kg/s", controls["m_dot"], data.index[0], 24, timedelta(hours=1)
    )
    result = scenario.run(
        plant, {"m_dot": profile}, 3600, base_inputs=controls | {"streams_in": streams}
    )
    assert len(result) == 24
    assert set(result.to_frame().columns.get_level_values(0)) == set(config.modules)
    changed = config.modules["filter_hot"].params[0].params | {"dp_nominal": 3200}
    config.modules["filter_hot"].params.append(
        DatedParams(valid_from=data.index[1], params=changed)
    )
    plant = build_plant(config, at=data.index[0])
    result = history.replay(plant, config, data.iloc[:2]).to_frame()
    assert (
        result["filter_hot", "pressure_drop"].iloc[1]
        > 1.99 * result["filter_hot", "pressure_drop"].iloc[0]
    )


def test_calibration_applies_only_when_requested(setup):
    """UA fitting improves a held-out window and application survives subsequent replay."""
    config, plant, data = setup
    before = plant.state_dict()
    fit = history.calibrate(plant, config, data, "heat_exchanger", ["ua"])
    assert fit.success and fit.rms_after < fit.rms_before / 100
    assert plant.state_dict() == before and not fit.applied
    fitted = history.calibrate(plant, config, data, "heat_exchanger", ["ua"], apply=True)
    history.replay(plant, config, data)
    assert plant.heat_exchanger.params.ua == fitted.fitted["ua"]
    with pytest.raises(ValueError, match="calibratable"):
        history.calibrate(plant, config, data, "heat_exchanger", ["not_a_param"])


def test_esp_coefficient_calibration(setup):
    """A broad synthetic calibration sweep recovers head predictions without modifying originals."""
    config, plant, data = setup
    pump = plant.doublet.esp
    rows = []
    for flow in np.linspace(90, 160, 16):
        row = data.iloc[0].to_dict()
        row["Qp"] = flow
        controls, streams, _ = twin.prepare(pump, config.bindings["doublet.esp"], row)
        predicted = pump(controls, streams).outputs
        row["ESP_Head"] = predicted.head * 0.8 / 1e5
        row["ESP_Pout"] = row["ESP_Pin"] + row["ESP_Head"]
        rows.append(row)
    observations = pd.DataFrame(rows, index=pd.date_range(data.index[0], periods=16, freq="15min"))
    fit = history.calibrate(plant, config, observations, "doublet.esp", ["head_coeff"])
    assert fit.success and fit.rms_after < 1e-8
    assert pump.params.head_coeff == config.modules["doublet.esp"].params[0].params["head_coeff"]
