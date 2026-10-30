"""Carnot COPs, sorption characteristic equations and part-load limits."""

import math

import pytest

from gemini.errors import PhysicsRangeError
from gemini.physics import refrigeration
from tests.fixtures.equivalence import assert_function_matches, assert_same_error


def test_carnot_cops_and_lift_floor():
    """Carnot COPs follow T/lift, differ by one at equal temperatures and honour the floor."""
    assert refrigeration.carnot_cop_heating(330, 290) == pytest.approx(330 / 40)
    assert refrigeration.carnot_cop_cooling(310, 280) == pytest.approx(280 / 30)
    heating = refrigeration.carnot_cop_heating(320, 280)
    assert heating - refrigeration.carnot_cop_cooling(320, 280) == pytest.approx(1)
    assert refrigeration.carnot_cop_heating(330, 325, 10) == pytest.approx(33)
    assert refrigeration.carnot_cop_cooling(300, 310, 10) == pytest.approx(31)
    assert refrigeration.carnot_cop_heating(330, 290, 10) == pytest.approx(330 / 40)


@pytest.mark.parametrize(
    "call, match",
    [
        (lambda: refrigeration.carnot_cop_heating(300, 300), "lift = 0"),
        (lambda: refrigeration.carnot_cop_cooling(290, 300), "lift = -10"),
        (lambda: refrigeration.carnot_cop_heating(300, 0), "source_temperature = 0"),
        (lambda: refrigeration.carnot_cop_cooling(300, 280, -1), "minimum_lift = -1"),
        (lambda: refrigeration.carnot_cop_heating(float("nan"), 280), "nan"),
    ],
)
def test_carnot_cops_reject_invalid_inputs(call, match):
    """Nonpositive temperatures or lifts and NaN raise PhysicsRangeError."""
    with pytest.raises(PhysicsRangeError, match=match):
        call()


def test_log_mean_temperature_and_lorenz_cop():
    """Log-mean temperatures lie between the end points; zero glides give the Carnot COP."""
    mean = refrigeration.log_mean_temperature(353.15, 303.15)
    assert mean == pytest.approx(50 / math.log(353.15 / 303.15))
    assert 303.15 < mean < (353.15 + 303.15) / 2
    assert refrigeration.log_mean_temperature(300, 300) == 300
    lorenz = refrigeration.lorenz_cop_heating(303.15, 353.15, 313.15, 290)
    sink = refrigeration.log_mean_temperature(303.15, 353.15)
    source = refrigeration.log_mean_temperature(313.15, 290)
    assert lorenz == pytest.approx(sink / (sink - source))
    flat = refrigeration.lorenz_cop_heating(330, 330, 290, 290)
    assert flat == refrigeration.carnot_cop_heating(330, 290)
    assert refrigeration.lorenz_cop_heating(330, 330, 325, 325, 10) == pytest.approx(33)


@pytest.mark.parametrize(
    "call, match",
    [
        (lambda: refrigeration.log_mean_temperature(0, 300), "inlet_temperature = 0"),
        (lambda: refrigeration.log_mean_temperature(300, float("nan")), "nan"),
        (lambda: refrigeration.lorenz_cop_heating(300, 300, 300, 300), "lift = 0"),
    ],
)
def test_lorenz_relations_reject_invalid_inputs(call, match):
    """Nonpositive temperatures, NaN and a nonpositive lift raise PhysicsRangeError."""
    with pytest.raises(PhysicsRangeError, match=match):
        call()


def test_characteristic_temperature_difference_uses_celsius():
    """The difference ddt = t_G - a t_AC + r t_E is evaluated on Celsius temperatures."""
    ddt = refrigeration.characteristic_temperature_difference(363.15, 303.15, 285.15, 2.5, 1.6)
    assert ddt == pytest.approx(90 - 2.5 * 30 + 1.6 * 12)
    ideal = refrigeration.characteristic_temperature_difference(360, 300, 280, 2.2, 1.2)
    assert ideal == pytest.approx(360 - 2.2 * 300 + 1.2 * 280)
    with pytest.raises(PhysicsRangeError, match="rejection_coefficient = nan"):
        refrigeration.characteristic_temperature_difference(360, 300, 280, math.nan, 1.2)


def test_characteristic_evaporator_duty_threshold_and_stopped_circuit():
    """Duty is linear above the threshold, damped by the sensitivity and zero otherwise."""
    assert refrigeration.characteristic_evaporator_duty(30, 10, 5000, 0) == 100000
    assert refrigeration.characteristic_evaporator_duty(30, 10, 5000, 1e-4) == pytest.approx(
        5000 * 20 / 1.5
    )
    assert refrigeration.characteristic_evaporator_duty(8, 10, 5000, 1e-4) == 0
    assert refrigeration.characteristic_evaporator_duty(30, 10, 5000, math.inf) == 0
    with pytest.raises(PhysicsRangeError, match="slope = -1"):
        refrigeration.characteristic_evaporator_duty(30, 10, -1, 0)


def test_characteristic_sensitivity_and_mean_temperature_consistency():
    """The closed-form duty satisfies Q_E = s (ddt_mean - ddt_min) at the mean temperatures."""
    rates = dict(generator=40000.0, rejection=100000.0, evaporator=50000.0)
    cop, auxiliary, a, r, slope = 0.7, 0.01, 2.2, 1.2, 20000.0
    duty = refrigeration.sorption_evaporator_capacity(
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
    mean = refrigeration.characteristic_temperature_difference(
        361.15 - duty / cop / rates["generator"] / 2,
        303.15 + rejection / rates["rejection"] / 2,
        285.15 - duty / rates["evaporator"] / 2,
        a,
        r,
    )
    assert duty == pytest.approx(slope * (mean - 10), rel=1e-12)
    sensitivity = refrigeration.characteristic_sensitivity(1, 1, 1, 2, 3, 2, 1)
    assert sensitivity == pytest.approx(2 / 2 + 2 * 3 / 2 + 1 / 2)
    assert refrigeration.characteristic_sensitivity(0, 1, 1, 2, 3, 2, 1) == math.inf
    with pytest.raises(PhysicsRangeError, match="expected all >= 0"):
        refrigeration.characteristic_sensitivity(-1, 1, 1, 2, 3, 2, 1)


def test_sorption_capacity_rejects_invalid_cop():
    """A nonpositive thermal COP or negative auxiliary ratio is outside the model."""
    with pytest.raises(PhysicsRangeError, match="thermal_cop = 0"):
        refrigeration.sorption_evaporator_capacity(
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


def test_part_load_duty():
    """Requests are capped at capacity and switched off below the minimum part load."""
    assert refrigeration.part_load_duty(5e5, 1e6, 0.2) == 5e5
    assert refrigeration.part_load_duty(2e6, 1e6, 0.2) == 1e6
    assert refrigeration.part_load_duty(1e5, 1e6, 0.2) == 0
    assert refrigeration.part_load_duty(0, 1e6, 0) == 0
    with pytest.raises(PhysicsRangeError, match="requested = -1"):
        refrigeration.part_load_duty(-1, 1e6, 0)
    with pytest.raises(PhysicsRangeError, match="minimum_part_load = 2"):
        refrigeration.part_load_duty(1, 1e6, 2)


NAN = math.nan


def test_carnot_and_lorenz_cops_on_arrays_match_floats():
    """Floored, unfloored, equal and glide temperatures agree on arrays and floats."""
    rows = [(350.0, 280.0, 10.0), (300.0, 295.0, 10.0), (300.0, 300.0, 5.0), (330.0, 290.0, 0.0)]
    assert_function_matches(refrigeration.carnot_cop_heating, rows)
    assert_function_matches(refrigeration.carnot_cop_cooling, rows)
    lorenz = [(300.0, 330.0, 285.0, 280.0, 10.0), (300.0, 300.0, 285.0, 285.0, 5.0)]
    assert_function_matches(refrigeration.lorenz_cop_heating, lorenz)
    assert_function_matches(refrigeration.log_mean_temperature, [(350.0, 340.0), (300.0, 300.0)])
    for function in (refrigeration.carnot_cop_heating, refrigeration.carnot_cop_cooling):
        for bad in [(0.0, 280.0, 1.0), (350.0, 280.0, -1.0), (280.0, 300.0, 0.0), (NAN, 1.0, 1.0)]:
            assert_same_error(function, [rows[0], bad], PhysicsRangeError)
    assert_same_error(
        refrigeration.log_mean_temperature, [(350.0, 340.0), (0.0, 300.0)], PhysicsRangeError
    )
    assert_same_error(
        refrigeration.log_mean_temperature, [(350.0, 340.0), (NAN, 300.0)], PhysicsRangeError
    )


def test_sorption_relations_on_arrays_match_floats():
    """Stopped, below-threshold and running sorption machines agree on arrays and floats."""
    assert_function_matches(
        refrigeration.characteristic_temperature_difference,
        [(360.0, 300.0, 285.0, 1.2, 1.1), (350.0, 310.0, 280.0, 2.0, 1.0)],
    )
    inf = math.inf
    duty_rows = [(10.0, 4.0, 1000.0, 0.01), (3.0, 4.0, 1000.0, 0.01), (10.0, 4.0, 1000.0, inf)]
    assert_function_matches(refrigeration.characteristic_evaporator_duty, duty_rows)
    assert_same_error(
        refrigeration.characteristic_evaporator_duty,
        [duty_rows[0], (10.0, 4.0, -1.0, 0.01)],
        PhysicsRangeError,
    )
    sensitivity_rows = [
        (100.0, 200.0, 300.0, 1.5, 2.5, 1.2, 1.1),
        (0.0, 200.0, 300.0, 1.5, 2.5, 1.2, 1.1),
        (100.0, 200.0, 0.0, 1.5, 2.5, 1.2, 1.1),
    ]
    assert_function_matches(refrigeration.characteristic_sensitivity, sensitivity_rows)
    assert_same_error(
        refrigeration.characteristic_sensitivity,
        [sensitivity_rows[0], (100.0, -2.0, 300.0, 1.5, 2.5, 1.2, 1.1)],
        PhysicsRangeError,
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
    assert_function_matches(refrigeration.sorption_evaporator_capacity, capacity_rows, **fixed)
    fixed_without_cop = {k: v for k, v in fixed.items() if k != "thermal_cop"}
    rows = [(360.0, 0.7), (360.0, 0.0)]
    assert_same_error(_capacity_of_cop, rows, PhysicsRangeError, **fixed_without_cop)


def _capacity_of_cop(generator_temperature, thermal_cop, **fixed):
    """Return the capacity of one machine whose thermal COP varies, so a check sees a row."""
    return refrigeration.sorption_evaporator_capacity(
        generator_temperature, 300.0, 285.0, 5e4, 6e4, 7e4, thermal_cop=thermal_cop, **fixed
    )


def test_part_load_duty_on_arrays_matches_floats():
    """Capped, below-minimum and passed-through duties agree on arrays and floats."""
    rows = [(50.0, 100.0, 0.2), (500.0, 100.0, 0.2), (10.0, 100.0, 0.2), (0.0, 100.0, 0.0)]
    assert_function_matches(refrigeration.part_load_duty, rows)
    for bad in [(-1.0, 100.0, 0.2), (1.0, 0.0, 0.2), (1.0, 100.0, 1.5), (1.0, 100.0, NAN)]:
        assert_same_error(refrigeration.part_load_duty, [rows[0], bad], PhysicsRangeError)
