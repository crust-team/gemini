"""Sorption characteristic equations and duties."""

import math

import pytest

from gemini.errors import PhysicsError
from gemini.modules.cooling import _physics
from gemini.physics import refrigeration
from tests.fixtures.equivalence import assert_function_matches, assert_same_error


def test_characteristic_temperature_difference_uses_celsius():
    """The difference ddt = t_G - a t_AC + r t_E is evaluated on Celsius temperatures."""
    ddt = _physics.characteristic_temperature_difference(363.15, 303.15, 285.15, 2.5, 1.6)
    assert ddt == pytest.approx(90 - 2.5 * 30 + 1.6 * 12)
    ideal = _physics.characteristic_temperature_difference(360, 300, 280, 2.2, 1.2)
    assert ideal == pytest.approx(360 - 2.2 * 300 + 1.2 * 280)
    with pytest.raises(PhysicsError, match="rejection_coefficient = nan"):
        _physics.characteristic_temperature_difference(360, 300, 280, math.nan, 1.2)


def test_characteristic_evaporator_duty_threshold_and_stopped_circuit():
    """Duty is linear above the threshold, damped by the sensitivity and zero otherwise."""
    assert _physics.characteristic_evaporator_duty(30, 10, 5000, 0) == 100000
    assert _physics.characteristic_evaporator_duty(30, 10, 5000, 1e-4) == pytest.approx(
        5000 * 20 / 1.5
    )
    assert _physics.characteristic_evaporator_duty(8, 10, 5000, 1e-4) == 0
    assert _physics.characteristic_evaporator_duty(30, 10, 5000, math.inf) == 0
    with pytest.raises(PhysicsError, match="slope = -1"):
        _physics.characteristic_evaporator_duty(30, 10, -1, 0)


def test_characteristic_sensitivity_and_mean_temperature_consistency():
    """The closed-form duty satisfies Q_E = s (ddt_mean - ddt_min) at the mean temperatures."""
    rates = dict(generator=40000.0, rejection=100000.0, evaporator=50000.0)
    cop, auxiliary, a, r, slope = 0.7, 0.01, 2.2, 1.2, 20000.0
    duty = _physics.sorption_evaporator_capacity(
        361.15,
        303.15,
        285.15,
        rates["generator"],
        rates["rejection"],
        rates["evaporator"],
        slope=slope,
        minimum_driving_difference=10,
        rejection_coefficient=a,
        evaporator_coefficient=r,
        thermal_cop=cop,
        auxiliary_power_ratio=auxiliary,
    )
    rejection = duty * (1 + 1 / cop + auxiliary)
    mean = _physics.characteristic_temperature_difference(
        361.15 - duty / cop / rates["generator"] / 2,
        303.15 + rejection / rates["rejection"] / 2,
        285.15 - duty / rates["evaporator"] / 2,
        a,
        r,
    )
    assert duty == pytest.approx(slope * (mean - 10), rel=1e-12)
    sensitivity = _physics.characteristic_sensitivity(1, 1, 1, 2, 3, 2, 1)
    assert sensitivity == pytest.approx(2 / 2 + 2 * 3 / 2 + 1 / 2)
    assert _physics.characteristic_sensitivity(0, 1, 1, 2, 3, 2, 1) == math.inf
    with pytest.raises(PhysicsError, match="expected all >= 0"):
        _physics.characteristic_sensitivity(-1, 1, 1, 2, 3, 2, 1)


def test_sorption_capacity_rejects_invalid_cop():
    """A nonpositive thermal COP or negative auxiliary ratio is outside the model."""
    with pytest.raises(PhysicsError, match="thermal_cop = 0"):
        _physics.sorption_evaporator_capacity(
            361.15,
            303.15,
            285.15,
            1,
            1,
            1,
            slope=1,
            minimum_driving_difference=10,
            rejection_coefficient=2,
            evaporator_coefficient=1,
            thermal_cop=0,
            auxiliary_power_ratio=0,
        )


def test_sorption_relations_on_arrays_match_floats():
    """Stopped, below-threshold and running sorption machines agree on arrays and floats."""
    assert_function_matches(
        _physics.characteristic_temperature_difference,
        [(360.0, 300.0, 285.0, 1.2, 1.1), (350.0, 310.0, 280.0, 2.0, 1.0)],
    )
    inf = math.inf
    duty_rows = [(10.0, 4.0, 1000.0, 0.01), (3.0, 4.0, 1000.0, 0.01), (10.0, 4.0, 1000.0, inf)]
    assert_function_matches(_physics.characteristic_evaporator_duty, duty_rows)
    assert_same_error(
        _physics.characteristic_evaporator_duty,
        [duty_rows[0], (10.0, 4.0, -1.0, 0.01)],
        PhysicsError,
    )
    sensitivity_rows = [
        (100.0, 200.0, 300.0, 1.5, 2.5, 1.2, 1.1),
        (0.0, 200.0, 300.0, 1.5, 2.5, 1.2, 1.1),
        (100.0, 200.0, 0.0, 1.5, 2.5, 1.2, 1.1),
    ]
    assert_function_matches(_physics.characteristic_sensitivity, sensitivity_rows)
    assert_same_error(
        _physics.characteristic_sensitivity,
        [sensitivity_rows[0], (100.0, -2.0, 300.0, 1.5, 2.5, 1.2, 1.1)],
        PhysicsError,
    )


def test_sorption_capacity_on_arrays_matches_floats():
    """A running, a below-threshold and a stopped machine agree on arrays and floats."""
    capacity_rows = [
        (360.0, 300.0, 285.0, 5e4, 6e4, 7e4),
        (330.0, 310.0, 285.0, 5e4, 6e4, 7e4),
        (360.0, 300.0, 285.0, 0.0, 6e4, 7e4),
    ]
    fixed = dict(
        slope=2000.0,
        minimum_driving_difference=20.0,
        rejection_coefficient=1.2,
        evaporator_coefficient=1.1,
        thermal_cop=0.7,
        auxiliary_power_ratio=0.02,
    )
    assert_function_matches(_physics.sorption_evaporator_capacity, capacity_rows, **fixed)
    fixed_without_cop = {k: v for k, v in fixed.items() if k != "thermal_cop"}
    rows = [(360.0, 0.7), (360.0, 0.0)]
    assert_same_error(_capacity_of_cop, rows, PhysicsError, **fixed_without_cop)


def _capacity_of_cop(generator_temperature, thermal_cop, **fixed):
    """Return the capacity of one machine whose thermal COP varies, so a check sees a row."""
    return _physics.sorption_evaporator_capacity(
        generator_temperature, 300.0, 285.0, 5e4, 6e4, 7e4, thermal_cop=thermal_cop, **fixed
    )


def test_sorption_duties_close_the_first_law():
    """Generator, electricity and rejection follow the thermal COP and the auxiliary ratio."""
    generator, electricity, rejection = _physics.sorption_duties(70.0, 0.7, 0.02)
    assert generator == pytest.approx(100)
    assert electricity == pytest.approx(1.4)
    assert rejection == pytest.approx(171.4)
    assert _physics.sorption_rejection_ratio(0.7, 0.02) == pytest.approx(171.4 / 70)
    assert refrigeration.coefficient_of_performance(70.0, 100.0) == pytest.approx(0.7)
    rows = [(70.0, 0.7, 0.02), (0.0, 0.55, 0.0)]
    assert_function_matches(_physics.sorption_duties, rows)
    assert_function_matches(_physics.sorption_rejection_ratio, [(0.7, 0.02), (0.55, 0.0)])
    assert_function_matches(refrigeration.coefficient_of_performance, [(70.0, 100.0), (1.0, 2.0)])


def test_sorption_delivered_duty_takes_the_smallest_limit():
    """The request, the characteristic equation and the capacity each limit the duty."""
    assert _physics.sorption_delivered_duty(100.0, 200.0, 300.0, 1.0) == (100.0, False)
    assert _physics.sorption_delivered_duty(100.0, 50.0, 300.0, 1.0) == (50.0, True)
    assert _physics.sorption_delivered_duty(300.0, 500.0, 200.0, 2.0) == (100.0, True)
    rows = [(100.0, 200.0, 300.0, 1.0), (100.0, 50.0, 300.0, 1.0), (300.0, 500.0, 200.0, 2.0)]
    assert_function_matches(_physics.sorption_delivered_duty, rows)
