"""Ideal-gas compression relations and their domain checks."""

import pytest

from gemini import ops
from gemini.errors import PhysicsError
from gemini.modules.pumps import _physics
from gemini.physics import constants, energy, pumps, units
from tests.fixtures.equivalence import assert_function_matches, assert_same_error


def test_isentropic_and_actual_stage_temperatures():
    """Air (k = 1.4) at a pressure ratio of 8 from 300 K reaches 543.4 K isentropically."""
    ideal = _physics.isentropic_outlet_temperature(300, 8, 1.4)
    assert ideal == pytest.approx(543.43, abs=0.01)
    assert _physics.stage_outlet_temperature(300, 8, 1.4, 0.8) == pytest.approx(
        300 + (ideal - 300) / 0.8
    )
    assert _physics.stage_outlet_temperature(300, 1, 1.4, 0.8) == 300


def test_multistage_work_splits_the_ratio_equally():
    """N intercooled stages do N times the work of one stage at the N-th root ratio."""
    one = _physics.specific_compression_work(300, 4, 1.4, 1005, 0.8, 1)
    two = _physics.specific_compression_work(300, 16, 1.4, 1005, 0.8, 2)
    assert two == pytest.approx(2 * one)
    assert two < _physics.specific_compression_work(300, 16, 1.4, 1005, 0.8, 1)
    assert _physics.specific_compression_work(300, 1, 1.4, 1005, 0.8, 3) == 0


@pytest.mark.parametrize(
    "arguments, match",
    [
        ((300, 0.5, 1.4, 1005, 0.8, 1), "pressure_ratio = 0.5"),
        ((0, 2, 1.4, 1005, 0.8, 1), "inlet_temperature = 0"),
        ((300, 2, 1.0, 1005, 0.8, 1), "heat_capacity_ratio = 1.0"),
        ((300, 2, 1.4, 1005, 0, 1), "isentropic_efficiency = 0"),
        ((300, 2, 1.4, 0.0, 0.8, 1), "specific_heat = 0"),
        ((300, 2, 1.4, 1005, 0.8, 0.0), "stages = 0"),
    ],
)
def test_out_of_domain_inputs_raise(arguments, match):
    """Expansion, nonpositive temperatures and invalid gas or machine data raise."""
    with pytest.raises(PhysicsError, match=match):
        _physics.specific_compression_work(*arguments)


def test_functions_match_on_arrays():
    """Each compression function on arrays equals one call per row."""
    assert_function_matches(
        _physics.isentropic_outlet_temperature, [(300, 8, 1.4), (350, 1, 1.3), (280, 2.5, 1.67)]
    )
    assert_function_matches(
        _physics.stage_outlet_temperature, [(300, 8, 1.4, 0.8), (350, 1, 1.3, 1.0)]
    )
    assert_function_matches(
        _physics.specific_compression_work,
        [(300, 4, 1.4, 1005, 0.8, 1), (300, 16, 1.4, 1005, 0.8, 2), (320, 1, 1.3, 2000, 0.7, 3)],
    )


@pytest.mark.parametrize(
    "function, rows",
    [
        (_physics.isentropic_outlet_temperature, [(300, 2, 1.4), (300, 2, 1.0)]),
        (_physics.isentropic_outlet_temperature, [(300, 2, 1.4), (0.0, 2.0, 1.4)]),
        (_physics.isentropic_outlet_temperature, [(300, 2, 1.4), (300, 0.5, 1.4)]),
        (_physics.stage_outlet_temperature, [(300, 2, 1.4, 0.8), (300, 2, 1.4, 1.5)]),
        (
            _physics.specific_compression_work,
            [(300, 2, 1.4, 1005, 0.8, 1.0), (300, 2, 1.4, 0.0, 0.8, 1.0)],
        ),
        (
            _physics.specific_compression_work,
            [(300, 2, 1.4, 1005.0, 0.8, 1.0), (300, 2, 1.4, 1005.0, 0.8, 0.0)],
        ),
    ],
)
def test_checks_match_on_arrays(function, rows):
    """A failing row raises the same error and message on arrays and on floats."""
    assert_same_error(function, rows, PhysicsError)


@ops.physics
def _work_when_running(running, specific_heat):
    """Return the work of a compressor that is off (zero heat capacity) on some rows."""
    work = _physics.specific_compression_work(300.0, 4.0, 1.4, specific_heat, 0.8, 2.0)
    return ops.where(running > 0, work, 0.0)


def test_a_failing_check_in_an_unselected_branch_is_dropped():
    """A stopped row with an invalid heat capacity gives zero on floats and on arrays."""
    rows = [(1.0, 1005.0), (0.0, 0.0), (0.0, -1.0)]
    assert_function_matches(_work_when_running, rows)


def test_stage_pressure_ratio_is_the_root_of_the_overall_ratio():
    """Four equal stages of ratio 2 give an overall ratio of 16."""
    assert _physics.stage_pressure_ratio(16.0, 4) == pytest.approx(2.0)
    assert _physics.stage_pressure_ratio(7.0, 1) == 7.0
    rows = [(16.0, 4.0), (7.0, 1.0), (1.0, 3.0), (30.0, 2.0)]
    assert_function_matches(_physics.stage_pressure_ratio, rows)


def test_overall_ratio_power_and_heat_rejected():
    """A 4 bar to 12 bar machine has ratio 3; 2 kg/s at 100 kJ/kg is 200 kW and rejects 0.5 P/N."""
    assert _physics.overall_pressure_ratio(12e5, 4e5) == pytest.approx(3)
    assert _physics.shaft_power(2.0, 1e5) == pytest.approx(2e5)
    assert _physics.heat_rejected(250e3, 200e3, 2) == pytest.approx(150e3)
    rows = [(250e3, 200e3), (0.0, 0.0)]
    assert_function_matches(_physics.heat_rejected, rows, stages=2)
    assert_function_matches(_physics.shaft_power, rows)
    assert_function_matches(_physics.overall_pressure_ratio, [(12e5, 4e5), (1e5, 1e5)])


def test_head_and_power_polynomials():
    """Coefficients act on bbl/day and give ft of head or bhp per stage at 60 Hz."""
    flow = units.bbl_per_day_to_m3s(1000)
    assert _physics.head(flow, 60, 1, [10, 0.01]) == pytest.approx(units.ft_head_to_pa(20))
    assert pumps.power(flow, 60, 1, [1, 0.001]) == pytest.approx(units.bhp_to_w(2))


def test_affinity_scaling_with_frequency_and_stages():
    """Head scales with stages and frequency squared, power with frequency cubed.

    At half the reference frequency, four stages give the head and eight stages the power of
    one stage at the reference frequency.
    """
    flow = units.bbl_per_day_to_m3s(500)
    head = _physics.head(flow, constants.ESP_REFERENCE_FREQUENCY, 1, [5, 0.02])
    power = pumps.power(flow, constants.ESP_REFERENCE_FREQUENCY, 1, [5, 0.02])
    assert _physics.head(flow, 30, 4, [5, 0.02]) == pytest.approx(head)
    assert pumps.power(flow, 30, 8, [5, 0.02]) == pytest.approx(power)


def test_polynomials_match_on_arrays():
    """Head and power on arrays equal one call per row, across frequencies and stage counts."""
    rows = [(0.0, 60.0, 1.0), (0.01, 45.0, 4.0), (0.05, 30.0, 8.0)]
    for function in (_physics.head, pumps.power):
        for coefficients in ([10, 0.01], [10, 0.01, -1e-6]):
            assert_function_matches(function, rows, coefficients=coefficients)


def test_power_chain_and_window():
    """Q H = 2000 W, shaft power 2500 W at 0.8, electricity 2778 W at 0.9."""
    hydraulic = pumps.hydraulic_power(0.02, 1e5)
    assert hydraulic == pytest.approx(2000)
    assert energy.input_power(hydraulic, 0.8) == pytest.approx(2500)
    assert energy.input_power(2500, 0.9) == pytest.approx(2500 / 0.9)
    assert pumps.speed_ratio(45, 60) == pytest.approx(0.75)
    assert _physics.line_shaft_friction_power(2.0, 100, 0.75) == pytest.approx(150)
    assert pumps.is_in_operating_window(0.02, 0.01, 0.04, 0.75)
    assert not pumps.is_in_operating_window(0.02, 0.04, 0.05, 0.75)


def test_efficiencies_are_zero_below_the_power_floor():
    """Both efficiency forms return zero for a stopped pump; the SI form is Q H / P."""
    assert _physics.pump_efficiency(0.02, 1e5, 2500.0) == pytest.approx(0.8)
    assert _physics.pump_efficiency(0.0, 0.0, 0.0) == 0
    assert _physics.esp_efficiency(0.0, 0.0, 0.0) == 0
    flow = units.bbl_per_day_to_m3s(1000)
    expected = 1000 / constants.ESP_EFFICIENCY_FLOW_FACTOR * 3.0 * _physics.HYDRAULIC_POWER_PER_HEAD
    assert _physics.esp_efficiency(flow, 3.0, 1.0) == pytest.approx(expected)


def test_new_functions_match_on_arrays():
    """Rows across the stopped and running branches agree with the traced run."""
    assert_function_matches(_physics.pump_efficiency, [(0.02, 1e5, 2500.0), (0.0, 0.0, 0.0)])
    assert_function_matches(_physics.esp_efficiency, [(0.02, 1e5, 2500.0), (0.0, 0.0, 0.0)])
    assert_function_matches(
        pumps.centrifugal_head, [(0.0, 0.5), (0.02, 1.0)], coefficients=[100.0, -3.0, -1.0]
    )
    assert_function_matches(
        pumps.is_in_operating_window, [(0.02, 0.01, 0.04, 0.75), (0.5, 0, 1, 0.1)]
    )


def test_constant_head_curves_give_the_design_head_and_power():
    """Any flow gets the head; the power is Q H / eta on the reference frequency."""
    head_curve, power_curve = pumps.constant_head_curves(40e5, 0.7)
    for flow in (0.02, 0.08):
        assert _physics.head(flow, 60.0, 1, head_curve) == pytest.approx(40e5)
        assert pumps.power(flow, 60.0, 1, power_curve) == pytest.approx(flow * 40e5 / 0.7)
