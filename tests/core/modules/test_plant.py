"""Explicit plant wiring, buried pump segmentation and diagram verification."""

from pathlib import Path

import pytest

from gemini.core.config.build import build_plant
from gemini.core.config.gemini_loader import load_gemini
from gemini.core.config.wiring import check_against_diagram, trace_wiring
from gemini.core.data.timeseries import CSVTimeSeries
from gemini.core.modes.twin import scenario_inputs
from gemini.core.modules.balance import collect_flows, energy_balance, mass_balance

DATA = Path(__file__).parents[3] / "datasets/geothermal_doublet"


def example():
    """Prepare one real operating point."""
    config = load_gemini(DATA)
    plant = build_plant(config)
    row = CSVTimeSeries(DATA / "geothermal_example_dataset.csv").frame.iloc[0]
    inputs, streams = scenario_inputs(plant, row)
    return plant, inputs, streams


def test_handwritten_wiring_and_split_helpers():
    """Every diagram link matches actual identities, including both sides of the buried ESP."""
    plant, inputs, streams = example()
    result = plant(inputs, streams)
    assert set(plant.last_results) == set(plant.config.modules)
    traced = trace_wiring(plant, inputs)
    assert len(traced) == 10
    assert check_against_diagram(traced, DATA / "diagram.json", plant.GEMINI_NODES) == []
    edge = next(iter(traced))
    assert check_against_diagram(traced - {edge}, DATA / "diagram.json", plant.GEMINI_NODES)
    assert check_against_diagram(
        traced | {("wrong", "out", "wrong", "in")}, DATA / "diagram.json", plant.GEMINI_NODES
    )
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
