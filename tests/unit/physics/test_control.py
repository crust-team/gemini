"""Ideal-form discrete PID relations: error sign, terms and clamping anti-windup."""

import pytest

from gemini.physics import control
from tests.fixtures.equivalence import assert_function_matches


def test_pid_terms_follow_the_ideal_form_by_hand():
    """K = 2, e = 3, I = 1, Td = 10 s, de = 0.5 over 5 s, Ti = 20 s, h = 4 s."""
    assert control.pid_error(10.0, 7.0, True) == 3.0
    assert control.pid_error(10.0, 7.0, False) == -3.0
    derivative = control.pid_derivative(2.0, 10.0, 0.5, 5.0)
    assert derivative == pytest.approx(2.0)
    assert control.pid_command(2.0, 3.0, 1.0, derivative) == pytest.approx(9.0)
    assert control.pid_integral_increment(2.0, 4.0, 20.0, 3.0) == pytest.approx(1.2)


def test_anti_windup_clamps_only_outward_increments():
    """Above the top limit a rising integral is frozen; a falling one is kept."""
    assert control.anti_windup_increment(0.5, 1.2, 0.0, 1.0) == 0.0
    assert control.anti_windup_increment(-0.5, 1.2, 0.0, 1.0) == -0.5
    assert control.anti_windup_increment(-0.5, -0.1, 0.0, 1.0) == 0.0
    assert control.anti_windup_increment(0.5, -0.1, 0.0, 1.0) == 0.5
    assert control.anti_windup_increment(0.5, 0.4, 0.0, 1.0) == 0.5


def test_pid_functions_match_on_arrays_over_every_branch():
    """Both directions and every clamp branch agree between floats and arrays."""
    assert_function_matches(
        control.pid_error, [(10.0, 7.0, True), (10.0, 7.0, False), (1.0, 4.0, True)]
    )
    assert_function_matches(control.pid_derivative, [(2.0, 10.0, 0.5, 5.0), (1.0, 0.0, -2.0, 1.0)])
    assert_function_matches(control.pid_command, [(2.0, 3.0, 1.0, 2.0), (0.5, -1.0, 0.0, 0.1)])
    assert_function_matches(control.pid_integral_increment, [(2.0, 4.0, 20.0, 3.0), (1, 1, 1, -1)])
    assert_function_matches(
        control.anti_windup_increment,
        [(0.5, 1.2, 0.0, 1.0), (-0.5, 1.2, 0.0, 1.0), (-0.5, -0.1, 0.0, 1.0), (0.5, 0.4, 0, 1)],
    )
