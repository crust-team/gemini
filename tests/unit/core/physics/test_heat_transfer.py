"""Pipe heat loss and heat-exchanger effectiveness relations."""

import json
from pathlib import Path

import pytest

from gemini.core.physics import heat_transfer
from gemini.errors import PhysicsRangeError
from tests.fixtures.equivalence import assert_function_matches, assert_same_error

GOLDEN = json.loads((Path(__file__).parents[3] / "fixtures/golden_values.json").read_text())


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
    assert heat_transfer.lmtd(10.0, 10.0) == 10
    assert heat_transfer.lmtd(10.0, 0.0) == 0
    assert heat_transfer.lmtd(20.0, 10.0) == pytest.approx(10 / 0.6931471805599453)
    assert heat_transfer.ntu(1000.0, 500.0) == 2
    with pytest.raises(PhysicsRangeError, match="dt2 = -1"):
        heat_transfer.lmtd(10, -1)
    with pytest.raises(PhysicsRangeError, match="c_min = 0"):
        heat_transfer.ntu(1000, 0)


def test_effectiveness_limits():
    """Counterflow and parallel effectiveness respect their limiting cases."""
    assert heat_transfer.effectiveness_counterflow(1e6, 0.5) == 1
    assert heat_transfer.effectiveness_counterflow(1.0, 1.0) == 0.5
    assert heat_transfer.effectiveness_counterflow(float("inf"), 1.0) == 1
    assert heat_transfer.effectiveness_counterflow(0.0, 0.5) == 0
    assert heat_transfer.effectiveness_parallel(1e6, 1.0) == 0.5
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
