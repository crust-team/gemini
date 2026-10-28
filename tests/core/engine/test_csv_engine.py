"""Offline engine integration against outputs captured from the original monitoring modules."""

import json
from pathlib import Path

import pytest

from gemini.core.data.csv_memory import CSVMemoryReader
from gemini.core.engine.mainmodule import MainModule
from gemini.core.plant.loader import setup

ROOT = Path(__file__).parents[3]


def test_one_csv_engine_step_and_restart():
    """Produce every old output tag, including ESP power, and avoid duplicate work on restart."""
    database = CSVMemoryReader(
        ROOT / "datasets/geothermal_example/geothermal_example_dataset.csv",
        end_time="2024-06-07T00:15:00Z",
    )
    plant = setup(str(ROOT / "datasets"), "geothermal_example", database=database)
    engine = MainModule(plant)
    engine.step()
    expected = json.loads((ROOT / "tests/golden/runtime_values.json").read_text())
    actual = {
        unit + ":" + tag: list(values.values()) for (unit, tag), values in database.outputs.items()
    }
    assert actual.keys() == expected.keys()
    for key in expected:
        assert actual[key] == pytest.approx(expected[key], rel=1e-9, abs=0), key
    engine.step()
    assert sum(len(values) for values in database.outputs.values()) == 8


def test_missing_suction_measurement_preserves_head_and_power():
    """The consolidated module does not discard calculable outputs when suction data is absent."""
    database = CSVMemoryReader(
        ROOT / "datasets/geothermal_example/geothermal_example_dataset.csv",
        end_time="2024-06-07T00:15:00Z",
    )
    database.driver.df.loc["2024-06-07T00:15:00Z", "ESP_Pin"] = None
    plant = setup(str(ROOT / "datasets"), "geothermal_example", database=database)
    MainModule(plant).step()
    assert list(database.outputs[("esp_1ee3", "esp_theoretical_power.calculated")].values()) == [
        0.0
    ]
    assert list(
        database.outputs[("esp_1ee3", "esp_theoretical_outlet_pressure.calculated")].values()
    ) == [None]
