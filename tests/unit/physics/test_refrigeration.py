"""Carnot COPs, sorption characteristic equations and part-load limits."""

import math

import pytest

from gemini.errors import PhysicsError
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
    """Nonpositive temperatures or lifts and NaN raise PhysicsError."""
    with pytest.raises(PhysicsError, match=match):
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
    """Nonpositive temperatures, NaN and a nonpositive lift raise PhysicsError."""
    with pytest.raises(PhysicsError, match=match):
        call()


def test_part_load_duty():
    """Requests are capped at capacity and switched off below the minimum part load."""
    assert refrigeration.part_load_duty(5e5, 1e6, 0.2) == 5e5
    assert refrigeration.part_load_duty(2e6, 1e6, 0.2) == 1e6
    assert refrigeration.part_load_duty(1e5, 1e6, 0.2) == 0
    assert refrigeration.part_load_duty(0, 1e6, 0) == 0
    with pytest.raises(PhysicsError, match="requested = -1"):
        refrigeration.part_load_duty(-1, 1e6, 0)
    with pytest.raises(PhysicsError, match="minimum_part_load = 2"):
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
            assert_same_error(function, [rows[0], bad], PhysicsError)
    assert_same_error(
        refrigeration.log_mean_temperature, [(350.0, 340.0), (0.0, 300.0)], PhysicsError
    )
    assert_same_error(
        refrigeration.log_mean_temperature, [(350.0, 340.0), (NAN, 300.0)], PhysicsError
    )


def test_part_load_duty_on_arrays_matches_floats():
    """Capped, below-minimum and passed-through duties agree on arrays and floats."""
    rows = [(50.0, 100.0, 0.2), (500.0, 100.0, 0.2), (10.0, 100.0, 0.2), (0.0, 100.0, 0.0)]
    assert_function_matches(refrigeration.part_load_duty, rows)
    for bad in [(-1.0, 100.0, 0.2), (1.0, 0.0, 0.2), (1.0, 100.0, 1.5), (1.0, 100.0, NAN)]:
        assert_same_error(refrigeration.part_load_duty, [rows[0], bad], PhysicsError)


def test_fraction_cops_scale_the_reversible_cops():
    """Each fraction COP is the efficiency times its reversible COP at the outlet temperatures."""
    args = (0.5, 10, 300, 330, 285, 280)
    assert refrigeration.carnot_fraction_cop_heating(*args) == 0.5 * 330 / 50
    assert refrigeration.carnot_fraction_cop_cooling(*args) == 0.5 * 280 / 50
    lorenz = refrigeration.lorenz_fraction_cop_heating(*args)
    assert lorenz == 0.5 * refrigeration.lorenz_cop_heating(300, 330, 285, 280, 10)
    rows = [
        (0.5, 10, 300, 330, 285, 280),
        (0.4, 5, 310, 340, 290, 288),
        (0.6, 10, 300, 305, 299, 298),
    ]
    for function in (
        refrigeration.carnot_fraction_cop_heating,
        refrigeration.carnot_fraction_cop_cooling,
        refrigeration.lorenz_fraction_cop_heating,
    ):
        assert_function_matches(function, rows)


def test_heat_pump_duties_close_the_first_law():
    """Evaporator plus electricity equals the condenser duty, from either side."""
    assert refrigeration.heating_evaporator_duty(900.0, 3.0) == pytest.approx(600)
    assert refrigeration.cooling_condenser_duty(600.0, 3.0) == pytest.approx(800)
    rows = [(900.0, 3.0), (100.0, 2.5)]
    assert_function_matches(refrigeration.heating_evaporator_duty, rows)
    assert_function_matches(refrigeration.cooling_condenser_duty, rows)


def test_carnot_heating_source_outlet_balances_the_evaporator():
    """The closed form satisfies C (T_in - x) = Q (1 - 1 / COP) on both lift branches."""
    for inlet, change, sink, lift in ((285.0, 4.0, 330.0, 10.0), (320.0, 4.0, 330.0, 10.0)):
        outlet = refrigeration.carnot_heating_source_outlet(inlet, change, sink, 0.5, lift)
        cop = 0.5 * sink / max(sink - outlet, lift)
        assert inlet - outlet == pytest.approx(change * (1 - 1 / cop))
    assert refrigeration.heating_cop_minimum_source(330.0, 0.5) == 165
    rows = [(285.0, 4.0, 330.0, 0.5, 10.0), (320.0, 4.0, 330.0, 0.5, 10.0)]
    assert_function_matches(refrigeration.carnot_heating_source_outlet, rows)


def test_carnot_cooling_sink_outlet_balances_the_condenser():
    """The closed form satisfies C (y - T_in) = Q (1 + 1 / COP) on both lift branches."""
    for inlet, change, source, lift in ((300.0, 3.0, 280.0, 10.0), (275.0, 3.0, 280.0, 10.0)):
        outlet, within_floor, denominator = refrigeration.carnot_cooling_sink_outlet(
            inlet, change, source, 0.5, lift
        )
        cop = 0.5 * source / max(outlet - source, lift)
        assert outlet - inlet == pytest.approx(change * (1 + 1 / cop))
        assert denominator == pytest.approx(1 - change / (0.5 * source))
    assert refrigeration.cooling_minimum_sink_rate(1400.0, 0.5, 280.0) == 10
    rows = [(300.0, 3.0, 280.0, 0.5, 10.0), (275.0, 3.0, 280.0, 0.5, 10.0)]
    assert_function_matches(refrigeration.carnot_cooling_sink_outlet, rows)


def test_lorenz_surplus_and_shortfall_vanish_at_the_balance():
    """The solver functions are zero where the evaporator balance closes."""
    outlet = 283.0
    cop = refrigeration.lorenz_fraction_cop_heating(0.5, 10, 300, 330, 288, outlet)
    duty = 1000.0
    rate = duty * (1 - 1 / cop) / (288 - outlet)
    surplus = refrigeration.lorenz_source_surplus(outlet, rate, 288, 300, 330, duty, 0.5, 10)
    assert surplus == pytest.approx(0, abs=1e-9)
    shortfall = refrigeration.source_limit_shortfall(
        refrigeration.carnot_fraction_cop_heating, 900.0, 300.0, 30.0, 288.0, 283.0, 100.0, 0.5, 10
    )
    sink_outlet = 300 + 900 / 30
    cop = 0.5 * sink_outlet / max(sink_outlet - 283, 10)
    assert shortfall == pytest.approx(900 * (1 - 1 / cop) - 100)
    rows = [
        (outlet, rate, 288, 300, 330, duty, 0.5, 10),
        (284.0, rate, 288, 300, 330, duty, 0.5, 10),
    ]
    assert_function_matches(refrigeration.lorenz_source_surplus, rows)

    def shortfall_rows(*row):
        return refrigeration.source_limit_shortfall(refrigeration.carnot_fraction_cop_heating, *row)

    shortfall_rows.__name__ = "source_limit_shortfall"
    assert_function_matches(shortfall_rows, [(900.0, 300.0, 30.0, 288.0, 283.0, 100.0, 0.5, 10)])
