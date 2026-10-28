"""Explicit plant wiring, buried pump segmentation and diagram verification."""

from pathlib import Path

import pytest

import gemini as gm
from gemini.core.modules.balance import collect_flows, energy_balance, mass_balance
from gemini.core.modules.wiring import trace_wiring

ROOT = Path(__file__).parents[2]
OLD = ROOT / "examples/legacy/gemini_project_bridge/old_project"


@pytest.fixture
def example(fresh_plant, fast_dataset):
    """Prepare one real operating point."""
    data = fast_dataset.window(end=fast_dataset.start)
    gm.Engine(on_error="raise").simulate(fresh_plant, data, gm.Clock.from_data(data))
    inputs = dict(fresh_plant.last_result.inputs) | dict(fresh_plant.last_result.inlets)
    return fresh_plant, inputs


def test_handwritten_wiring_and_split_helpers(example):
    """Every diagram link matches actual identities, including both sides of the buried ESP."""
    plant, inputs = example
    result = plant(**inputs)
    assert set(plant.last_results) == {
        path for path, module in plant.named_modules() if path and not module._children
    }
    traced = trace_wiring(plant, inputs)
    assert len(traced) == 10
    project = gm.legacy.read_project(OLD)
    assert gm.legacy.check_wiring(plant, project) == []
    well = plant.doublet.well
    bottom = plant.last_results["doublet.reservoir"].outlets["sandface"]
    assert well.intake_conditions(bottom) == plant.last_results["doublet.well"].outlets["wellhead"]
    discharge = plant.last_results["doublet.esp"].outlets["discharge"]
    assert (
        well.wellhead_from_discharge(discharge)
        == plant.last_results["doublet.riser"].outlets["wellhead"]
    )
    assert result.outputs.electricity_use == collect_flows(result)["electricity"]
    assert result.outputs.cop == pytest.approx(
        result.outputs.thermal_power / result.outputs.electricity_use
    )
    assert mass_balance(plant, result)["relative_residual"] < 1e-12
    balance = energy_balance(plant, result)
    assert balance["relative_thermal_residual"] < 1e-12
    assert balance["residual"] == pytest.approx(result.outputs.electricity_use)


def test_trace_hooks_are_removed_after_failure(example):
    """Failed evaluation does not leak observers into subsequent calls."""
    plant, inputs = example
    before = [(len(m._hooks), len(m._pre_hooks)) for m in plant.modules()]
    plant.injection_pump.pressure_setpoint = 0
    with pytest.raises(ValueError):
        trace_wiring(plant, inputs)
    assert before == [(len(m._hooks), len(m._pre_hooks)) for m in plant.modules()]
    plant.injection_pump.pressure_setpoint = 5.15e6
    plant(**inputs)
