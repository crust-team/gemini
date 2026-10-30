"""Binary cycle design and energy balance."""

import math

import pytest

from gemini.physics import power_cycles
from tests.fixtures.equivalence import assert_function_matches

DESIGN = dict(
    brine_heat_capacity=4200.0,
    ambient_temperature=285.0,
    condenser_approach=15.0,
    pinch=5.0,
    minimum_outlet_temperature=340.0,
    fraction_of_carnot=0.5,
    capacity=1e6,
)


def test_lorenz_efficiency_is_one_minus_condensing_over_log_mean():
    """The Lorenz efficiency equals 1 - T_c / T_lm for T_a = 400 K, T_b = 340 K, T_c = 300 K."""
    log_mean = (400 - 340) / math.log(400 / 340)
    assert power_cycles.lorenz_efficiency(400, 340, 300) == pytest.approx(1 - 300 / log_mean)


def test_cycle_design_caps_and_stops():
    """A large flow is capped at the capacity; a cold brine gives no power."""
    capped = power_cycles.cycle_design(400.0, 500.0, **DESIGN)
    assert capped.is_capped and capped.processed_share < 1
    cold = power_cycles.cycle_design(330.0, 10.0, **DESIGN)
    assert (cold.cycle_efficiency, cold.processed_share, cold.is_capped) == (0, 0, False)


def test_plant_balance_closes_the_first_law():
    """Heat input equals gross power plus condenser duty and net power plus heat loss."""
    balance = power_cycles.plant_balance(1000.0, 0.1, 0.2)
    assert balance.gross_power == pytest.approx(100)
    assert balance.electricity_generated == pytest.approx(80)
    assert balance.condenser_duty + balance.gross_power == pytest.approx(1000)
    assert balance.electricity_generated + balance.heat_loss == pytest.approx(1000)
    assert balance.thermal_efficiency == pytest.approx(0.08)


def test_brine_outlet_temperature_mixes_the_bypass():
    """Half the brine cooled from 400 K to 340 K gives 370 K."""
    assert power_cycles.brine_outlet_temperature(400, 0.5, 340) == pytest.approx(370)


def test_rows_match_arrays():
    """Design rows across running, capped and stopped agree with the traced run."""
    rows = [(400.0, 500.0), (400.0, 5.0), (330.0, 10.0)]
    assert_function_matches(power_cycles.cycle_design, rows, **DESIGN)
    assert_function_matches(power_cycles.lorenz_efficiency, [(400.0, 340.0, 300.0)])
    assert_function_matches(
        power_cycles.plant_balance, [(1000.0, 0.1), (0.0, 0.0)], parasitic_fraction=0.2
    )
    assert_function_matches(
        power_cycles.brine_outlet_temperature, [(400.0, 0.5, 340.0), (330.0, 0.0, 340.0)]
    )
