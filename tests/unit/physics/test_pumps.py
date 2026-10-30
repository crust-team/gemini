"""TNO pump polynomials on the historical US basis."""

import pytest

from gemini.physics import constants, energy, pumps, units
from tests.fixtures.equivalence import assert_function_matches


def test_head_and_power_polynomials():
    """Coefficients act on bbl/day and give ft of head or bhp per stage at 60 Hz."""
    flow = units.bbl_per_day_to_m3s(1000)
    assert pumps.head(flow, 60, 1, [10, 0.01]) == pytest.approx(units.ft_head_to_pa(20))
    assert pumps.power(flow, 60, 1, [1, 0.001]) == pytest.approx(units.bhp_to_w(2))


def test_affinity_scaling_with_frequency_and_stages():
    """Head scales with stages and frequency squared, power with frequency cubed.

    At half the reference frequency, four stages give the head and eight stages the power of
    one stage at the reference frequency.
    """
    flow = units.bbl_per_day_to_m3s(500)
    head = pumps.head(flow, constants.ESP_REFERENCE_FREQUENCY, 1, [5, 0.02])
    power = pumps.power(flow, constants.ESP_REFERENCE_FREQUENCY, 1, [5, 0.02])
    assert pumps.head(flow, 30, 4, [5, 0.02]) == pytest.approx(head)
    assert pumps.power(flow, 30, 8, [5, 0.02]) == pytest.approx(power)


def test_polynomials_match_on_arrays():
    """Head and power on arrays equal one call per row, across frequencies and stage counts."""
    rows = [(0.0, 60.0, 1.0), (0.01, 45.0, 4.0), (0.05, 30.0, 8.0)]
    for function in (pumps.head, pumps.power):
        for coefficients in ([10, 0.01], [10, 0.01, -1e-6]):
            assert_function_matches(function, rows, coefficients=coefficients)


def test_centrifugal_curve_and_parabolic_efficiency():
    """At half speed the head curve drops to c0/4 at zero flow; efficiency peaks at the bep."""
    assert pumps.centrifugal_head(0.0, 0.5, [100.0, 0.0, -1.0]) == pytest.approx(25)
    assert pumps.centrifugal_head(2.0, 1.0, [100.0, -3.0, -1.0]) == pytest.approx(90)
    load = pumps.best_efficiency_ratio(0.03, 0.5, 0.06)
    assert load == pytest.approx(1)
    assert pumps.parabolic_efficiency(0.8, load) == pytest.approx(0.8)
    assert pumps.parabolic_efficiency(0.8, 0.5) == pytest.approx(0.6)


def test_power_chain_and_window():
    """Q H = 2000 W, shaft power 2500 W at 0.8, electricity 2778 W at 0.9."""
    hydraulic = pumps.hydraulic_power(0.02, 1e5)
    assert hydraulic == pytest.approx(2000)
    assert energy.input_power(hydraulic, 0.8) == pytest.approx(2500)
    assert energy.input_power(2500, 0.9) == pytest.approx(2500 / 0.9)
    assert pumps.speed_ratio(45, 60) == pytest.approx(0.75)
    assert pumps.line_shaft_friction_power(2.0, 100, 0.75) == pytest.approx(150)
    assert pumps.in_operating_window(0.02, 0.01, 0.04, 0.75)
    assert not pumps.in_operating_window(0.02, 0.04, 0.05, 0.75)


def test_efficiencies_are_zero_below_the_power_floor():
    """Both efficiency forms return zero for a stopped pump; the SI form is Q H / P."""
    assert pumps.pump_efficiency(0.02, 1e5, 2500.0) == pytest.approx(0.8)
    assert pumps.pump_efficiency(0.0, 0.0, 0.0) == 0
    assert pumps.esp_efficiency(0.0, 0.0, 0.0) == 0
    flow = units.bbl_per_day_to_m3s(1000)
    expected = 1000 / constants.ESP_EFFICIENCY_FLOW_FACTOR * 3.0 * pumps.HYDRAULIC_POWER_PER_HEAD
    assert pumps.esp_efficiency(flow, 3.0, 1.0) == pytest.approx(expected)


def test_new_functions_match_on_arrays():
    """Rows across the stopped and running branches agree with the traced run."""
    assert_function_matches(pumps.pump_efficiency, [(0.02, 1e5, 2500.0), (0.0, 0.0, 0.0)])
    assert_function_matches(pumps.esp_efficiency, [(0.02, 1e5, 2500.0), (0.0, 0.0, 0.0)])
    assert_function_matches(
        pumps.centrifugal_head, [(0.0, 0.5), (0.02, 1.0)], coefficients=[100.0, -3.0, -1.0]
    )
    assert_function_matches(pumps.in_operating_window, [(0.02, 0.01, 0.04, 0.75), (0.5, 0, 1, 0.1)])
