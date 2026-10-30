"""Saturation pressure, dew point, humidity ratio and wet bulb against reference values."""

import math

import numpy as np
import pytest

from gemini import backends
from gemini.core.physics import psychrometrics
from gemini.errors import PhysicsRangeError
from gemini.graph import Graph, Interpreter
from tests.fixtures.equivalence import assert_function_matches, assert_same_error

C = 273.15


@pytest.mark.parametrize(
    "celsius, kilopascal",
    [
        (-20, 0.10326),
        (-10, 0.25990),
        (10, 1.2282),
        (20, 2.3392),
        (30, 4.2470),
        (40, 7.3849),
        (50, 12.352),
        (100, 101.42),
    ],
)
def test_saturation_pressure_matches_ashrae_table(celsius, kilopascal):
    """Hyland-Wexler agrees with ASHRAE Fundamentals (2017) chapter 1 table 3 within 3e-4."""
    assert psychrometrics.saturation_pressure(celsius + C) == pytest.approx(
        kilopascal * 1e3, rel=3e-4
    )


def test_saturation_pressure_switches_from_ice_to_water_at_zero_celsius():
    """Below 0 degC the pressure is over ice, which is lower than over supercooled water."""
    assert psychrometrics.saturation_pressure(C) == pytest.approx(611.21, rel=1e-4)
    assert psychrometrics.saturation_pressure(C - 1e-9) == pytest.approx(611.15, rel=1e-4)


@pytest.mark.parametrize(
    "celsius, relative_humidity, dew_celsius",
    [(24, 0.5, 12.95), (20, 0.5, 9.27), (30, 0.8, 26.17), (20, 0.1, -11.18)],
)
def test_dew_point_reference_values(celsius, relative_humidity, dew_celsius):
    """The dew point matches psychrometric-chart values; below 0 degC it is the frost point."""
    dew = psychrometrics.dew_point(celsius + C, relative_humidity)
    assert dew - C == pytest.approx(dew_celsius, abs=0.01)


def test_dew_point_inverts_the_saturation_pressure():
    """Saturated air has its own temperature as dew point, and the inversion is consistent."""
    assert psychrometrics.dew_point(300.0, 1.0) == 300.0
    dew = psychrometrics.dew_point(300.0, 0.37)
    assert psychrometrics.saturation_pressure(dew) == pytest.approx(
        0.37 * psychrometrics.saturation_pressure(300.0), rel=1e-9
    )


def test_humidity_ratio():
    """W = 0.621945 p_w / (p - p_w); saturated values lie 0.4 % below ASHRAE's W_s column."""
    p_w = 0.5 * psychrometrics.saturation_pressure(25 + C)
    assert psychrometrics.humidity_ratio(25 + C, 0.5, 101325) == pytest.approx(
        0.621945 * p_w / (101325 - p_w)
    )
    assert psychrometrics.humidity_ratio(20 + C, 1, 101325) == pytest.approx(0.014758, rel=6e-3)
    assert psychrometrics.humidity_ratio(30 + C, 1, 101325) == pytest.approx(0.027329, rel=6e-3)
    assert psychrometrics.humidity_ratio(20 + C, 0, 101325) == 0


def test_wet_bulb_temperature():
    """Stull (2011) gives 13.7 degC at 20 degC and 50 %; saturated air is near its dry bulb."""
    assert psychrometrics.wet_bulb_temperature(20 + C, 0.5) - C == pytest.approx(13.7, abs=0.05)
    assert psychrometrics.wet_bulb_temperature(30 + C, 0.99) - C == pytest.approx(30, abs=0.65)
    dry = psychrometrics.wet_bulb_temperature(35 + C, 0.2)
    assert 18 + C < dry < 35 + C


@pytest.mark.parametrize(
    "call, message",
    [
        (lambda: psychrometrics.saturation_pressure(500), "temperature = 500"),
        (lambda: psychrometrics.saturation_pressure(float("nan")), "temperature = nan"),
        (lambda: psychrometrics.dew_point(300, 0), "relative_humidity = 0"),
        (lambda: psychrometrics.dew_point(300, 1.2), "relative_humidity = 1.2"),
        (lambda: psychrometrics.dew_point(300, 1e-9), "expected a dew point above"),
        (lambda: psychrometrics.humidity_ratio(300, -0.1, 101325), "relative_humidity = -0.1"),
        (lambda: psychrometrics.humidity_ratio(373.15, 1, 1e5), "pressure = 100000"),
        (lambda: psychrometrics.wet_bulb_temperature(330, 0.5), "temperature = 330"),
        (lambda: psychrometrics.wet_bulb_temperature(300, 0.01), "relative_humidity = 0.01"),
        (lambda: psychrometrics.wet_bulb_temperature(300, float("nan")), "= nan"),
    ],
)
def test_out_of_range_inputs_raise(call, message):
    """Inputs outside each correlation's domain raise PhysicsRangeError."""
    with pytest.raises(PhysicsRangeError, match=message):
        call()


DEW_POINT_ROWS = [
    (300.0, 0.5),
    (300.0, 1.0),
    (200.0, 0.4),
    (173.15, 1.0),
    (473.15, 0.2),
    (260.0, 0.05),
    (280.0, 0.999999),
    (350.0, 0.7),
]


def test_dew_point_on_arrays_matches_floats_on_every_branch():
    """Frost point, dew point and the saturated shortcut agree on arrays and floats."""
    assert_function_matches(psychrometrics.dew_point, DEW_POINT_ROWS)


def test_dew_point_on_a_dense_grid_stays_within_the_documented_tolerance():
    """The vectorised Brent follows the scalar solve over temperature and humidity."""
    temperature, humidity = np.meshgrid(np.linspace(180, 473, 40), np.linspace(0.05, 1, 40))
    rows = list(zip(temperature.ravel().tolist(), humidity.ravel().tolist()))
    floats = []
    for row in rows:
        try:
            floats.append(psychrometrics.dew_point(*row))
        except PhysicsRangeError:
            floats.append(math.nan)
    valid = np.isfinite(floats)
    columns = [np.array(column)[valid] for column in zip(*rows)]
    np.testing.assert_allclose(
        psychrometrics.dew_point(*columns), np.array(floats)[valid], rtol=1e-12, atol=0
    )


@pytest.mark.parametrize(
    "rows",
    [
        [(300.0, 0.5), (100.0, 0.5), (500.0, 0.5)],
        [(300.0, 0.5), (300.0, 0.0), (300.0, 1.2)],
        [(300.0, 0.5), (300.0, 1e-9)],
        [(300.0, 0.5), (math.nan, 0.5)],
        [(300.0, math.nan)],
    ],
)
def test_dew_point_rows_raise_the_error_of_the_float_path(rows):
    """The first failing row raises the same class and message on arrays."""
    assert_same_error(psychrometrics.dew_point, rows, PhysicsRangeError)


def test_dew_point_in_a_graph_runs_the_solver_and_raises_the_check_error():
    """A traced dew point equals the floats; a row without a root raises its own message."""
    graph = Graph("dew_point")
    temperature = graph.input("temperature", "inlet")
    humidity = graph.input("humidity", "inlet")
    graph.output("dew", psychrometrics.dew_point(temperature, humidity))
    run = Interpreter(graph, backends.get("numpy")).run
    rows = DEW_POINT_ROWS
    columns = {
        "temperature": np.array([r[0] for r in rows]),
        "humidity": np.array([r[1] for r in rows]),
    }
    expected = [psychrometrics.dew_point(*row) for row in rows]
    np.testing.assert_allclose(run(columns)["dew"], expected, rtol=1e-12, atol=0)
    with pytest.raises(PhysicsRangeError, match="expected a dew point above"):
        run({"temperature": np.array([300.0, 300.0]), "humidity": np.array([0.5, 1e-9])})
