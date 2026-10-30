"""Plant-level series read from the leaf columns of a run."""

import math

import pytest

import gemini as gm
from gemini.analysis import series
from gemini.core.modules import CoolingConsumer, HeatConsumer
from tests.fixtures.result_tables import make_results


@pytest.fixture(scope="module")
def consumers():
    """Return a plant with one heat and two cooling consumers and a run over three hours."""
    plant = gm.Plant("Demo")
    plant.add("HeatConsumer", "heat")
    plant.add("CoolingConsumer", "cool_a")
    plant.add("CoolingConsumer", "cool_b")
    results = make_results(
        {
            "heat": {"heat_supplied": [1.0, 2.0, math.nan]},
            "cool_a": {"heat_absorbed": [10.0, 20.0, math.nan]},
            "cool_b": {"heat_absorbed": [1.0, math.nan, math.nan]},
            "pump": {"electricity": [5.0, 5.0, 5.0]},
        },
        step=1800.0,
    )
    return plant, results


def test_window_seconds_are_the_tick_durations(consumers):
    """Each tick lasts the step of the run."""
    assert series.window_seconds(consumers[1]).tolist() == [1800.0] * 3


def test_leaf_total_sums_the_leaves_of_one_class(consumers):
    """Cooling consumers add up, a heat consumer is not among them, a missing tick is NaN."""
    plant, results = consumers
    frame = results.to_frame()
    cold = series.leaf_total(plant, frame, "heat_absorbed", CoolingConsumer)
    assert cold.iloc[0] == 11.0
    assert cold.iloc[1] == 20.0
    assert math.isnan(cold.iloc[2])
    heat = series.leaf_total(plant, frame, "heat_supplied", HeatConsumer)
    assert heat.iloc[:2].tolist() == [1.0, 2.0]


def test_leaf_total_is_none_without_a_declaring_leaf(consumers):
    """A field no leaf of the class declares gives no series."""
    plant, results = consumers
    assert series.leaf_total(plant, results.to_frame(), "heat_supplied", CoolingConsumer) is None


def test_results_total_sums_by_field_name(consumers):
    """The electricity column is found without the plant."""
    _, results = consumers
    total = series.results_total(results, results.to_frame(), "electricity")
    assert total.tolist() == [5.0, 5.0, 5.0]
    assert series.results_total(results, results.to_frame(), "fuel") is None


def test_energy_integrates_power_and_skips_missing_ticks(consumers):
    """Energy is power times duration, over the ticks that have a value."""
    plant, results = consumers
    heat = series.leaf_total(plant, results.to_frame(), "heat_supplied", HeatConsumer)
    assert series.energy(heat, series.window_seconds(results)) == (1.0 + 2.0) * 1800.0
