"""Carnot COPs, sorption characteristic equations and part-load limits."""

import math

import pytest

from gemini.core.physics import refrigeration
from gemini.errors import PhysicsRangeError


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
