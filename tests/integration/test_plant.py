"""Explicit plant wiring, buried pump segmentation and diagram verification."""

from pathlib import Path

import pandas as pd
import pytest

import gemini as gm
from examples.shared.doublet_heat.plant import DoubletHeatPlant
from gemini.core.modules.balance import collect_flows, energy_balance, mass_balance
from gemini.core.modules.wiring import trace_wiring

ROOT = Path(__file__).parents[2]
SHARED = ROOT / "examples/shared/doublet_heat"
OLD = ROOT / "examples/legacy/gemini_project_bridge/old_project"


def example():
    """Prepare one real operating point."""
    plant = DoubletHeatPlant.load(SHARED / "plant.json")
    frame = pd.read_csv(SHARED / "doublet_2024_15min.csv", parse_dates=["time"])
    data = gm.Dataset.from_frame(frame.iloc[:1], time_column="time")
    data = data.window(end=data.start)
    gm.Engine(on_error="raise").simulate(plant, data, gm.Clock.from_data(data))
    inputs, streams = plant.last_result.inputs.model_dump(), plant.last_result.inlets
    return plant, inputs, streams


def test_handwritten_wiring_and_split_helpers():
    """Every diagram link matches actual identities, including both sides of the buried ESP."""
    plant, inputs, streams = example()
    result = plant(inputs, streams)
    assert set(plant.last_results) == {
        path for path, module in plant.named_modules() if path and not module._children
    }
    traced = trace_wiring(plant, inputs)
    assert len(traced) == 10
    project = gm.legacy.read_project(OLD)
    assert gm.legacy.check_wiring(plant, project) == []
    well = plant.doublet.well
    bottom = plant.last_results["doublet.reservoir"].streams["sandface"]
    assert well.intake_conditions(bottom) == plant.last_results["doublet.well"].streams["wellhead"]
    discharge = plant.last_results["doublet.esp"].streams["discharge"]
    assert (
        well.wellhead_from_discharge(discharge)
        == plant.last_results["doublet.riser"].streams["wellhead"]
    )
    assert result.outputs.electricity == collect_flows(result)["electricity"]
    assert result.outputs.cop == pytest.approx(
        result.outputs.thermal_power / result.outputs.electricity
    )
    assert mass_balance(plant, result)["relative_residual"] < 1e-12
    balance = energy_balance(plant, result)
    assert balance["relative_thermal_residual"] < 1e-12
    assert balance["residual"] == pytest.approx(result.outputs.electricity)


def test_trace_hooks_are_removed_after_failure():
    """Failed evaluation does not leak observers into subsequent calls."""
    plant, inputs, _ = example()
    before = [(len(m._hooks), len(m._pre_hooks)) for m in plant.modules()]
    with pytest.raises(ValueError):
        trace_wiring(plant, inputs | {"injection_pressure": 0})
    assert before == [(len(m._hooks), len(m._pre_hooks)) for m in plant.modules()]
    plant(inputs)
