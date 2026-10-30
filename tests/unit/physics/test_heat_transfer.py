"""Pipe heat loss and heat-exchanger effectiveness relations."""

import json
import math
from pathlib import Path

import pytest

from gemini.errors import PhysicsRangeError
from gemini.physics import heat_transfer
from tests.fixtures.equivalence import assert_function_matches, assert_same_error

GOLDEN = json.loads((Path(__file__).parents[2] / "fixtures/golden_values.json").read_text())


def test_pipe_temperature_change_golden_and_balance():
    """The explicit energy balance reproduces the golden and UA*dT = m*cp*dT."""
    u = GOLDEN["temperature"]["inputs"]
    assert heat_transfer.pipe_temperature_change(
        u[0], u[1], u[6], u[2], u[3], u[4], u[5], u[7]
    ) == pytest.approx(GOLDEN["temperature"]["expected"], rel=1e-9)
    change = heat_transfer.pipe_temperature_change(350, 10, 20, 40, 0, 4200, 800, 300)
    assert change * 40 * 4200 == pytest.approx(10 * 20 * 50)
    assert heat_transfer.pipe_temperature_change(300, 10, 20, 40, 0, 4200, 800, 300) == 0
    with pytest.raises(PhysicsRangeError, match="total mass flow = 0"):
        heat_transfer.pipe_temperature_change(350, 10, 20, 1, -1, 4200, 800, 300)


def test_lmtd_and_ntu():
    """LMTD handles equal and pinched terminals; NTU is UA over C_min."""
    assert heat_transfer.lmtd(10, 10) == 10
    assert heat_transfer.lmtd(10, 0) == 0
    assert heat_transfer.lmtd(20, 10) == pytest.approx(10 / 0.6931471805599453)
    assert heat_transfer.ntu(1000, 500) == 2
    with pytest.raises(PhysicsRangeError, match="dt2 = -1"):
        heat_transfer.lmtd(10, -1)
    with pytest.raises(PhysicsRangeError, match="c_min = 0"):
        heat_transfer.ntu(1000, 0)


def test_effectiveness_limits():
    """Counterflow and parallel effectiveness respect their limiting cases."""
    assert heat_transfer.effectiveness_counterflow(1e6, 0.5) == 1
    assert heat_transfer.effectiveness_counterflow(1, 1) == 0.5
    assert heat_transfer.effectiveness_counterflow(float("inf"), 1) == 1
    assert heat_transfer.effectiveness_counterflow(0, 0.5) == 0
    assert heat_transfer.effectiveness_parallel(1e6, 1) == 0.5
    with pytest.raises(PhysicsRangeError, match="c_ratio = 2"):
        heat_transfer.effectiveness_parallel(1, 2)


@pytest.mark.parametrize(
    "call",
    [
        lambda: heat_transfer.lmtd(float("nan"), 3),
        lambda: heat_transfer.ntu(float("nan"), 3),
        lambda: heat_transfer.effectiveness_counterflow(float("nan"), 0.5),
        lambda: heat_transfer.effectiveness_parallel(1, float("nan")),
    ],
)
def test_nan_inputs_are_rejected(call):
    """Reject NaN inputs, which formerly returned NaN as if it were a valid result."""
    with pytest.raises(PhysicsRangeError, match="nan"):
        call()


def test_pipe_temperature_change_on_arrays_matches_floats():
    """Single-phase, mixed and reverse flows agree on arrays and floats."""
    rows = [
        (350.0, 10.0, 20.0, 40.0, 0.0, 4200.0, 800.0, 300.0),
        (350.0, 10.0, 20.0, 30.0, 10.0, 4200.0, 800.0, 300.0),
        (300.0, 10.0, 20.0, -40.0, 0.0, 4200.0, 800.0, 310.0),
    ]
    assert_function_matches(heat_transfer.pipe_temperature_change, rows)
    assert_same_error(
        heat_transfer.pipe_temperature_change,
        [rows[0], (350.0, 10.0, 20.0, 1.0, -1.0, 4200.0, 800.0, 300.0)],
        PhysicsRangeError,
    )


def test_lmtd_on_arrays_matches_floats_on_every_branch():
    """Equal, pinched, ordinary and reversed terminal differences agree."""
    rows = [(10.0, 10.0), (10.0, 0.0), (0.0, 5.0), (0.0, 0.0), (20.0, 10.0), (3.0, 40.0)]
    assert_function_matches(heat_transfer.lmtd, rows)
    assert_same_error(heat_transfer.lmtd, [(10.0, 5.0), (10.0, -1.0)], PhysicsRangeError)
    assert_same_error(heat_transfer.lmtd, [(10.0, 5.0), (float("nan"), 1.0)], PhysicsRangeError)


def test_ntu_on_arrays_matches_floats():
    """The ratio agrees, and a zero capacity rate or NaN raises the same error."""
    assert_function_matches(heat_transfer.ntu, [(1000.0, 500.0), (0.0, 10.0), (5.0, 1e-3)])
    assert_same_error(heat_transfer.ntu, [(1.0, 2.0), (1.0, 0.0)], PhysicsRangeError)
    assert_same_error(heat_transfer.ntu, [(1.0, 2.0), (-1.0, 3.0)], PhysicsRangeError)
    assert_same_error(heat_transfer.ntu, [(1.0, 2.0), (float("nan"), 3.0)], PhysicsRangeError)


@pytest.mark.parametrize(
    "function", [heat_transfer.effectiveness_counterflow, heat_transfer.effectiveness_parallel]
)
def test_effectiveness_on_arrays_matches_floats(function):
    """Balanced, unbalanced, zero and infinite NTU agree on arrays and floats."""
    rows = [(1.0, 1.0), (0.0, 0.5), (2.5, 0.0), (3.0, 0.7), (float("inf"), 1.0), (1e6, 0.5)]
    assert_function_matches(function, rows)
    assert_same_error(function, [(1.0, 0.5), (1.0, 2.0)], PhysicsRangeError)
    assert_same_error(function, [(1.0, 0.5), (-1.0, 0.5)], PhysicsRangeError)
    assert_same_error(function, [(1.0, 0.5), (1.0, float("nan"))], PhysicsRangeError)


def test_signed_parts_split_a_value_into_its_positive_and_negative_sizes():
    """A positive value has no negative part, a negative one no positive part, zero neither."""
    assert heat_transfer.signed_parts(3.0) == (3.0, 0)
    assert heat_transfer.signed_parts(-2.0) == (0, 2.0)
    assert heat_transfer.signed_parts(0.0) == (0.0, -0.0)
    assert_function_matches(heat_transfer.signed_parts, [(3.0,), (-2.0,), (0.0,)])


def test_logarithmic_mean_by_hand():
    """The mean of 20 and 10 is 10 / ln 2."""
    assert heat_transfer.logarithmic_mean(20.0, 10.0) == pytest.approx(10 / math.log(2))
    assert_function_matches(heat_transfer.logarithmic_mean, [(20.0, 10.0), (3.0, 40.0)])


def test_heat_rate_and_setpoint_duty():
    """A 2 kW/K stream heated 5 K takes 10 kW; a gap below zero needs no heat."""
    assert heat_transfer.heat_rate(2000.0, 5.0) == 10000.0
    assert heat_transfer.setpoint_duty(2000.0, 5.0) == 10000.0
    assert heat_transfer.setpoint_duty(2000.0, -3.0) == 0.0
    rows = [(2000.0, 5.0), (2000.0, -3.0), (0.0, 4.0), (10.0, 0.0)]
    assert_function_matches(heat_transfer.setpoint_duty, rows)
    assert_function_matches(heat_transfer.heat_rate, rows)


def test_temperature_change_is_duty_over_capacity_rate_and_zero_when_stopped():
    """10 kW into 2 kW/K gives 5 K; a stopped stream gives zero."""
    assert heat_transfer.temperature_change(10000.0, 2000.0) == 5.0
    assert heat_transfer.temperature_change(10000.0, 0.0) == 0.0
    rows = [(10000.0, 2000.0), (-500.0, 100.0), (10.0, 0.0), (0.0, 0.0)]
    assert_function_matches(heat_transfer.temperature_change, rows)


def test_effectiveness_outlet_temperature_by_hand():
    """Half effectiveness moves a 350 K stream halfway to 300 K."""
    assert heat_transfer.effectiveness_outlet_temperature(350.0, 0.5, 300.0) == 325.0
    rows = [(350.0, 0.5, 300.0), (280.0, 1.0, 300.0), (300.0, 0.0, 350.0)]
    assert_function_matches(heat_transfer.effectiveness_outlet_temperature, rows)


def test_ambient_effectiveness_is_one_minus_exp_of_minus_ntu_and_zero_when_stopped():
    """UA = C gives 1 - 1/e; a stopped stream, even with conductance, gives zero."""
    assert heat_transfer.ambient_effectiveness(100.0, 100.0) == pytest.approx(1 - math.exp(-1))
    assert heat_transfer.ambient_effectiveness(100.0, 0.0) == 0.0
    rows = [(100.0, 100.0), (0.0, 50.0), (100.0, 0.0), (1e6, 1.0), (5.0, 1e-3)]
    assert_function_matches(heat_transfer.ambient_effectiveness, rows)
    assert_same_error(
        heat_transfer.ambient_effectiveness, [(1.0, 2.0), (-1.0, 3.0)], PhysicsRangeError
    )


def test_relaxation_matches_the_lumped_capacitance_solution():
    """After one time constant the gap to equilibrium is 1/e of the start."""
    factor = heat_transfer.relaxation_factor(10.0, 100.0, 1000.0)
    assert factor == pytest.approx(math.exp(-1))
    assert heat_transfer.exponential_relaxation(310.0, 300.0, factor) == pytest.approx(
        300.0 + 10.0 * math.exp(-1)
    )
    rows = [(10.0, 100.0, 1000.0), (0.0, 100.0, 1000.0), (5.0, 0.0, 10.0)]
    assert_function_matches(heat_transfer.relaxation_factor, rows)
    assert_function_matches(
        heat_transfer.exponential_relaxation, [(310.0, 300.0, 0.5), (280.0, 300.0, 0.0)]
    )


def test_mixed_temperature_weights_by_capacity_rate_and_averages_when_stopped():
    """Equal 1 kW/K streams at 300 and 320 K mix at 310 K; stopped streams give the mean."""
    assert heat_transfer.mixed_temperature(1000.0, 300.0, 1000.0, 320.0) == 310.0
    assert heat_transfer.mixed_temperature(3000.0, 300.0, 1000.0, 340.0) == 310.0
    assert heat_transfer.mixed_temperature(0.0, 300.0, 0.0, 320.0) == 310.0
    rows = [(1000.0, 300.0, 1000.0, 320.0), (3000.0, 300.0, 0.0, 340.0), (0.0, 300.0, 0.0, 320.0)]
    assert_function_matches(heat_transfer.mixed_temperature, rows)


def test_terminal_differences_for_both_arrangements():
    """Counterflow pairs the hot inlet with the cold outlet; parallel flow with the cold inlet."""
    assert heat_transfer.terminal_differences(350.0, 330.0, 300.0, 320.0, True) == (30.0, 30.0)
    assert heat_transfer.terminal_differences(350.0, 330.0, 300.0, 320.0, False) == (50.0, 10.0)
    for flag in (True, False):
        rows = [(350.0, 330.0, 300.0, 320.0), (340.0, 310.0, 290.0, 300.0)]
        assert_function_matches(heat_transfer.terminal_differences, rows, counterflow=flag)


def test_apparent_conductance_by_hand_and_every_code():
    """A 20 kW exchanger with 30 K terminal differences has UA = 20000 / 30."""
    good = (350.0, 330.0, 300.0, 320.0, 0.5, 0.5, 2000.0, 2000.0)
    result = heat_transfer.apparent_conductance("counterflow", *good)
    assert result[0] == pytest.approx(20000.0 / 30.0)
    assert result[1] == heat_transfer.DETERMINED
    rows = [
        good,
        (350.0, 330.0, 300.0, 320.0, 0.0, 0.5, 2000.0, 2000.0),
        (350.0, 330.0, 300.0, 320.0, 0.5, 0.25, 2000.0, 2000.0),
        (350.0, 330.0, 330.0, 350.0, 0.5, 0.5, 2000.0, 2000.0),
    ]
    codes = [heat_transfer.apparent_conductance("counterflow", *row)[1] for row in rows]
    assert codes == [
        heat_transfer.DETERMINED,
        heat_transfer.NONPOSITIVE_INPUT,
        heat_transfer.DISAGREEING_DUTIES,
        heat_transfer.NO_LMTD,
    ]
    for arrangement in ("counterflow", "parallel"):

        def apparent(*row, arrangement=arrangement):
            return heat_transfer.apparent_conductance(arrangement, *row)

        apparent.__name__ = f"apparent_conductance_{arrangement}"
        assert_function_matches(apparent, rows if arrangement == "counterflow" else rows[:3])


def test_exchanger_balance_matches_effectiveness_ntu():
    """The balance conserves energy and gives zero for a stopped stream, in both arrangements."""
    effectiveness, units_, duty, hot_out, cold_out = heat_transfer.exchanger_balance(
        350.0, 300.0, 1000.0, 2000.0, 1000.0, True
    )
    assert units_ == 1
    assert effectiveness == pytest.approx((1 - math.exp(-0.5)) / (1 - 0.5 * math.exp(-0.5)))
    assert duty == pytest.approx(effectiveness * 1000 * 50)
    assert hot_out == 350 - duty / 1000 and cold_out == 300 + duty / 2000
    stopped = heat_transfer.exchanger_balance(350.0, 300.0, 0.0, 2000.0, 1000.0, False)
    assert stopped == (0.0, 0.0, 0.0, 350.0, 300.0)
    for counterflow in (True, False):
        rows = [(350.0, 300.0, 1000.0, 2000.0, 1000.0), (350.0, 300.0, 0.0, 2000.0, 1000.0)]
        assert_function_matches(heat_transfer.exchanger_balance, rows, counterflow=counterflow)


def test_conductance_ratio_and_mean_temperature():
    """The fouling ratio is UA over the design UA; the mean is arithmetic."""
    assert heat_transfer.conductance_ratio(80.0, 100.0) == 0.8
    assert heat_transfer.mean_temperature(300.0, 310.0) == 305
    assert_function_matches(heat_transfer.conductance_ratio, [(80.0, 100.0), (120.0, 100.0)])
    assert_function_matches(heat_transfer.mean_temperature, [(300.0, 310.0), (280.0, 300.0)])


def test_sensible_latent_loads_serve_the_sensible_load_first():
    """Short capacity cuts the latent load; a dry coil has none; fans scale with the duty."""
    assert heat_transfer.sensible_latent_loads(100.0, 60.0, 60.0, False) == (60.0, 40.0)
    assert heat_transfer.sensible_latent_loads(100.0, 120.0, 60.0, False) == (100.0, 0.0)
    assert heat_transfer.sensible_latent_loads(100.0, 60.0, 30.0, True) == (60.0, 0.0)
    rows = [(100.0, 60.0, 60.0), (100.0, 120.0, 60.0), (100.0, 60.0, 30.0)]
    for dry in (True, False):
        assert_function_matches(heat_transfer.sensible_latent_loads, rows, is_dry=dry)
    assert heat_transfer.fan_power(1000.0, 0.02) == 20
    assert_function_matches(heat_transfer.fan_power, [(1000.0, 0.02), (0.0, 0.02)])
