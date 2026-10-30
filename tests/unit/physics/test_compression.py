"""Ideal-gas compression relations and their domain checks."""

import pytest

from gemini import ops
from gemini.errors import PhysicsError
from gemini.physics import compression
from tests.fixtures.equivalence import assert_function_matches, assert_same_error


def test_isentropic_and_actual_stage_temperatures():
    """Air (k = 1.4) at a pressure ratio of 8 from 300 K reaches 543.4 K isentropically."""
    ideal = compression.isentropic_outlet_temperature(300, 8, 1.4)
    assert ideal == pytest.approx(543.43, abs=0.01)
    assert compression.stage_outlet_temperature(300, 8, 1.4, 0.8) == pytest.approx(
        300 + (ideal - 300) / 0.8
    )
    assert compression.stage_outlet_temperature(300, 1, 1.4, 0.8) == 300


def test_multistage_work_splits_the_ratio_equally():
    """N intercooled stages do N times the work of one stage at the N-th root ratio."""
    one = compression.specific_compression_work(300, 4, 1.4, 1005, 0.8, 1)
    two = compression.specific_compression_work(300, 16, 1.4, 1005, 0.8, 2)
    assert two == pytest.approx(2 * one)
    assert two < compression.specific_compression_work(300, 16, 1.4, 1005, 0.8, 1)
    assert compression.specific_compression_work(300, 1, 1.4, 1005, 0.8, 3) == 0


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
        compression.specific_compression_work(*arguments)


def test_functions_match_on_arrays():
    """Each compression function on arrays equals one call per row."""
    assert_function_matches(
        compression.isentropic_outlet_temperature, [(300, 8, 1.4), (350, 1, 1.3), (280, 2.5, 1.67)]
    )
    assert_function_matches(
        compression.stage_outlet_temperature, [(300, 8, 1.4, 0.8), (350, 1, 1.3, 1.0)]
    )
    assert_function_matches(
        compression.specific_compression_work,
        [(300, 4, 1.4, 1005, 0.8, 1), (300, 16, 1.4, 1005, 0.8, 2), (320, 1, 1.3, 2000, 0.7, 3)],
    )


@pytest.mark.parametrize(
    "function, rows",
    [
        (compression.isentropic_outlet_temperature, [(300, 2, 1.4), (300, 2, 1.0)]),
        (compression.isentropic_outlet_temperature, [(300, 2, 1.4), (0.0, 2.0, 1.4)]),
        (compression.isentropic_outlet_temperature, [(300, 2, 1.4), (300, 0.5, 1.4)]),
        (compression.stage_outlet_temperature, [(300, 2, 1.4, 0.8), (300, 2, 1.4, 1.5)]),
        (
            compression.specific_compression_work,
            [(300, 2, 1.4, 1005, 0.8, 1.0), (300, 2, 1.4, 0.0, 0.8, 1.0)],
        ),
        (
            compression.specific_compression_work,
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
    work = compression.specific_compression_work(300.0, 4.0, 1.4, specific_heat, 0.8, 2.0)
    return ops.where(running > 0, work, 0.0)


def test_a_failing_check_in_an_unselected_branch_is_dropped():
    """A stopped row with an invalid heat capacity gives zero on floats and on arrays."""
    rows = [(1.0, 1005.0), (0.0, 0.0), (0.0, -1.0)]
    assert_function_matches(_work_when_running, rows)


def test_stage_pressure_ratio_is_the_root_of_the_overall_ratio():
    """Four equal stages of ratio 2 give an overall ratio of 16."""
    assert compression.stage_pressure_ratio(16.0, 4) == pytest.approx(2.0)
    assert compression.stage_pressure_ratio(7.0, 1) == 7.0
    rows = [(16.0, 4.0), (7.0, 1.0), (1.0, 3.0), (30.0, 2.0)]
    assert_function_matches(compression.stage_pressure_ratio, rows)


def test_overall_ratio_power_and_heat_rejected():
    """A 4 bar to 12 bar machine has ratio 3; 2 kg/s at 100 kJ/kg is 200 kW and rejects 0.5 P/N."""
    assert compression.overall_pressure_ratio(12e5, 4e5) == pytest.approx(3)
    assert compression.shaft_power(2.0, 1e5) == pytest.approx(2e5)
    assert compression.heat_rejected(250e3, 200e3, 2) == pytest.approx(150e3)
    rows = [(250e3, 200e3), (0.0, 0.0)]
    assert_function_matches(compression.heat_rejected, rows, stages=2)
    assert_function_matches(compression.shaft_power, rows)
    assert_function_matches(compression.overall_pressure_ratio, [(12e5, 4e5), (1e5, 1e5)])
