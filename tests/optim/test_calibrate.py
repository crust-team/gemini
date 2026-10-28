"""Calibration application, public replay objective and scalar/vector fits."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import gemini as gm
from gemini.core.engine.step import prepare

DATA = Path(__file__).parents[2] / "datasets/geothermal_doublet"


def test_hx_apply_and_save(tmp_path):
    """Optional application preserves histories and fitted parameters survive replay/save."""
    plant = gm.load_plant(DATA)
    dataset = gm.Dataset.from_csv(DATA / "geothermal_example_dataset.csv").window(
        end="2024-06-07T02:45Z"
    )
    before = plant.state_dict()
    fit = gm.optim.calibrate(plant, dataset, "heat_exchanger", ["ua"], apply=False)
    assert fit.success and fit.rms_after < fit.rms_before / 100
    assert plant.state_dict() == before and not fit.applied
    count = len(plant.heat_exchanger.param_history)
    fitted = gm.optim.calibrate(plant, dataset, "heat_exchanger", ["ua"])
    gm.Engine().replay(plant, dataset)
    assert plant.heat_exchanger.params.ua == fitted.fitted["ua"]
    assert len(plant.heat_exchanger.param_history) == count
    plant.save(tmp_path / "plant.json")
    loaded = gm.load_plant(tmp_path / "plant.json")
    assert loaded.state_dict() == plant.state_dict()
    assert loaded.heat_exchanger.param_history == plant.heat_exchanger.param_history
    assert loaded.bindings == plant.bindings
    with pytest.raises(ValueError, match="calibratable"):
        gm.optim.calibrate(plant, dataset, "heat_exchanger", ["no_such_field"])


def test_esp_head_coefficients():
    """Recover a synthetic curve across a broad flow sweep without changing the original."""
    plant = gm.load_plant(DATA)
    source = gm.Dataset.from_csv(DATA / "geothermal_example_dataset.csv")
    first = source.read(source.start, source.start).iloc[0]
    pump = plant.doublet.esp
    original = pump.params.head_coeff.copy()
    rows = []
    for flow in np.linspace(90, 160, 16):
        row = first.to_dict()
        row["Qp"] = flow
        controls, streams, _ = prepare(pump, plant.bindings["doublet.esp"], row)
        predicted = pump(controls, streams).outputs
        row["ESP_Head"] = predicted.head * 0.8 / 1e5
        row["ESP_Pout"] = row["ESP_Pin"] + row["ESP_Head"]
        rows.append(row)
    data = gm.Dataset.from_frame(
        pd.DataFrame(rows, index=pd.date_range(source.start, periods=16, freq="15min"))
    )
    fit = gm.optim.calibrate(plant, data, "doublet.esp", ["head_coeff"], apply=False)
    assert fit.success and fit.rms_after < 1e-8
    assert pump.params.head_coeff == original
    assert fit.observations == 16
    print(fit)
