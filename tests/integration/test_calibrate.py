"""Calibration application, public replay objective and scalar/vector fits."""

import numpy as np
import pandas as pd
import pytest

import gemini as gm
from examples.shared.doublet_heat.plant import DoubletHeatPlant
from gemini.core.engine.step import prepare


def test_hx_apply_and_save(tmp_path, fresh_plant, reference_dataset):
    """Optional application preserves histories and fitted parameters survive replay/save."""
    plant, dataset = fresh_plant, reference_dataset
    dataset = dataset.window(end="2024-06-07T02:45Z")
    before = plant.state_dict()
    fit = gm.optim.calibrate(
        plant, dataset, params=[plant.get_parameter("heat_exchanger.ua")], apply=False
    )
    assert fit.success and fit.rms_after < fit.rms_before / 100
    assert plant.state_dict() == before and not fit.applied
    count = len(plant.heat_exchanger.param_history)
    fitted = gm.optim.calibrate(plant, dataset, params=[plant.get_parameter("heat_exchanger.ua")])
    gm.Engine().replay(plant, dataset)
    assert plant.heat_exchanger.ua == fitted.fitted["ua"]
    assert len(plant.heat_exchanger.param_history) == count
    plant.save(tmp_path / "plant.json")
    loaded = DoubletHeatPlant.load(tmp_path / "plant.json")
    assert loaded.state_dict() == plant.state_dict()
    assert loaded.heat_exchanger.param_history == plant.heat_exchanger.param_history
    assert loaded.bindings == plant.bindings
    with pytest.raises(ValueError, match="calibratable"):
        gm.optim.calibrate(
            plant,
            dataset,
            params=[
                plant.get_parameter("heat_exchanger.ua"),
                plant.get_parameter("heat_exchanger.arrangement"),
            ],
        )


def test_esp_head_coefficients(fresh_plant, fast_dataset):
    """Recover a synthetic curve across a broad flow sweep without changing the original."""
    plant, source = fresh_plant, fast_dataset
    first = source.read(source.start, source.start).iloc[0]
    pump = plant.doublet.esp
    original = pump.head_coeff.copy()
    rows = []
    for flow in np.linspace(90, 160, 16):
        row = first.to_dict()
        row["doublet.esp.suction.m_dot"] = flow / 3600
        kwargs, _ = prepare(pump, plant.bindings["doublet.esp"], row)
        predicted = pump(**kwargs).outputs
        row["doublet.esp.head"] = predicted.head * 0.8
        row["doublet.esp.discharge_pressure"] = (
            row["doublet.esp.suction.p"] + row["doublet.esp.head"]
        )
        rows.append(row)
    data = gm.Dataset.from_frame(
        pd.DataFrame(rows, index=pd.date_range(source.start, periods=16, freq="15min"))
    )
    fit = gm.optim.calibrate(
        plant, data, params=[plant.get_parameter("doublet.esp.head_coeff")], apply=False
    )
    assert fit.success and fit.rms_after < 1e-8
    assert pump.head_coeff == original
    assert fit.observations == 16
    print(fit)
