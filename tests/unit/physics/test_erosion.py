"""Erosion rate correlations, API velocity limit and their input domain."""

import json
import math
from pathlib import Path

import numpy as np
import pytest

from gemini import ops
from gemini.errors import PhysicsRangeError, UnknownCorrelationError
from gemini.physics import erosion, units
from tests.fixtures.equivalence import assert_function_matches, assert_same_error

GOLDEN = json.loads((Path(__file__).parents[2] / "fixtures/golden_values.json").read_text())
FLOW = dict(flow_rate=units.m3h_to_m3s(150), rho_fluid=1068, diameter=0.1778)


@pytest.mark.parametrize("model", ["DNV", "OKA", "TULSA", "API"])
def test_erosion_golden(model):
    """SI rate/velocity boundaries preserve original erosion results."""
    case = GOLDEN["erosion_" + model]
    if model == "API":
        result = erosion.api_erosional_velocity(1068)
        expected = case["expected"]["erosion_velocity_ms"]
    else:
        result = erosion.erosion_rate(model, **FLOW)
        expected = case["expected"]["erosion_rate_mm_yr"]
    assert result == pytest.approx(expected, rel=1e-9, abs=0)


def test_model_aliases_are_case_insensitive():
    """Legacy spellings select the same correlation."""
    assert erosion.erosion_rate("dnvgl", **FLOW) == erosion.erosion_rate("DNV", **FLOW)
    assert erosion.erosion_rate(" E/CRC Tulsa ", **FLOW) == erosion.erosion_rate("TULSA", **FLOW)
    assert erosion.erosion_rate("ecrc", **FLOW) == erosion.erosion_rate("TULSA", **FLOW)
    with pytest.raises(UnknownCorrelationError, match="velocity limit"):
        erosion.erosion_rate("API", **FLOW)
    with pytest.raises(UnknownCorrelationError, match="'X'"):
        erosion.erosion_rate("X", **FLOW)


def test_dnv_materials_and_retained_titanium_rejection():
    """Softer composites erode faster; titanium stays unreachable (retained decision)."""
    steel = erosion.erosion_rate("DNV", **FLOW, material="Steel")
    epoxy = erosion.erosion_rate("DNV", **FLOW, material="GRP/epoxy")
    vinyl = erosion.erosion_rate("DNV", **FLOW, material="grp/vinyl ester")
    assert steel > 0 and epoxy > 0 and vinyl == pytest.approx(2 * epoxy)
    with pytest.raises(UnknownCorrelationError, match="'titanium'"):
        erosion.erosion_rate("DNV", **FLOW, material="titanium")


def test_oka_particles_and_tulsa_inputs():
    """OKA particle tables and Tulsa shape factor scale the rate as published."""
    rates = {p: erosion.erosion_rate("OKA", **FLOW, particle_material=p) for p in ("sio2", "SiC")}
    assert all(rate > 0 for rate in rates.values())
    assert erosion.erosion_rate("OKA", **FLOW, particle_material="glass") > 0
    with pytest.raises(UnknownCorrelationError, match="'sand'"):
        erosion.erosion_rate("OKA", **FLOW, particle_material="sand")
    base = erosion.erosion_rate("TULSA", **FLOW)
    assert erosion.erosion_rate("TULSA", **FLOW, shape_factor=1.0) == pytest.approx(2 * base)


@pytest.mark.parametrize("model", ["DNV", "OKA", "TULSA"])
def test_zero_flow_erodes_nothing_and_bad_inputs_raise(model):
    """Zero flow gives zero; a negative flow or zero angle formerly crashed."""
    assert erosion.erosion_rate(model, **(FLOW | {"flow_rate": 0.0})) == 0
    with pytest.raises(PhysicsRangeError, match="complex rate"):
        erosion.erosion_rate(model, **(FLOW | {"flow_rate": -0.04}))
    with pytest.raises(PhysicsRangeError, match="alpha = 0"):
        erosion.erosion_rate(model, **FLOW, alpha=0)


def test_api_velocity_limit_and_comparison():
    """API RP 14E limit falls with density; comparisons report ratio, margin and alarm."""
    limit = erosion.api_erosional_velocity(1068)
    assert erosion.api_erosional_velocity(1068 / 4) == pytest.approx(2 * limit)
    assert erosion.api_erosional_velocity(1) == pytest.approx(
        units.API_VELOCITY_FACTOR * 125 / math.sqrt(1)
    )
    result = erosion.api_velocity_comparison(limit / 2, limit)
    assert result == {
        "velocity_ratio": 0.5,
        "velocity_margin_ms": limit / 2,
        "exceeds_api_limit": False,
    }
    with pytest.raises(PhysicsRangeError, match="rho_fluid = 0"):
        erosion.api_erosional_velocity(0)
    with pytest.raises(PhysicsRangeError, match="limit = 0"):
        erosion.api_velocity_comparison(1, 0)


def test_dnv_year_constant_converts_metres_per_second_to_millimetres_per_year():
    """The DNV rate scales its penetration speed [m/s] by 1000 mm/m * 365.25 * 86400 s/year.

    Upstream code uses ``C_unit = 1000 * (3600 * 24 * 365.25)`` = 3.15576e10 as well. The
    upstream Sphinx page writes 31.5576e6, the seconds of a year alone (m/s to m/year), under a
    mm/year label: a documentation typo that would understate the rate by a factor of 1000.
    """
    seconds_per_year = 365.25 * 86400
    assert units.ms_to_mm_year(1) == pytest.approx(3.15576e10, rel=1e-15)
    assert units.ms_to_mm_year(1) == pytest.approx(1000 * seconds_per_year, rel=1e-15)
    assert 31.5576e6 == pytest.approx(seconds_per_year, rel=1e-15)
    rate = erosion.erosion_rate("DNV", **FLOW)
    area = math.pi * FLOW["diameter"] ** 2 / 4
    mass_flow = FLOW["flow_rate"] * FLOW["rho_fluid"]
    velocity = mass_flow / (FLOW["rho_fluid"] * area)
    alpha = math.pi / 2
    coefficients = (9.37, -42.295, 110.864, -175.804, 170.137, -98.398, 31.211, -4.17)
    angle_function = sum(c * alpha ** (i + 1) for i, c in enumerate(coefficients))
    penetration = mass_flow * 2e-9 * velocity**2.6 * angle_function / (7800 * area)
    assert rate == pytest.approx(penetration * 3.15576e10, rel=1e-9)
    assert rate / (penetration * 31.5576e6) == pytest.approx(1000, rel=1e-9)


ROWS = [
    (0.0, 1068, 0.1778, math.pi / 2),
    (units.m3h_to_m3s(150), 1068, 0.1778, math.pi / 2),
    (units.m3h_to_m3s(300), 900, 0.1, 0.5),
    (0.02, 1200, 0.2, 1.2),
]


def _rate(model, **fixed):
    def rate(flow_rate, rho_fluid, diameter, alpha):
        return erosion.erosion_rate(
            model,
            flow_rate=flow_rate,
            rho_fluid=rho_fluid,
            diameter=diameter,
            alpha=alpha,
            **fixed,
        )

    return rate


@pytest.mark.parametrize(
    "model, fixed",
    [
        ("DNV", {}),
        ("DNV", {"material": "grp/epoxy"}),
        ("OKA", {}),
        ("OKA", {"particle_material": "glass", "hardness": 2e9}),
        ("OKA", {"particle_material": "SiC"}),
        ("TULSA", {}),
        ("TULSA", {"shape_factor": 1.0, "rho_pipe": 8000}),
    ],
)
def test_erosion_rate_matches_arrays(model, fixed):
    """Each correlation gives the same numbers on arrays as per row."""
    rate = _rate(model, **fixed)
    assert_function_matches(rate, ROWS)


def test_erosion_rate_errors_match_arrays():
    """Negative flow and zero angle raise the same message on arrays as on floats."""
    bad_flow = ROWS[:2] + [(-0.04, 1068, 0.1778, math.pi / 2)]
    bad_angle = ROWS[:2] + [(0.04, 1068, 0.1778, 0.0)]
    for model in ("DNV", "OKA", "TULSA"):
        assert_same_error(_rate(model), bad_flow, PhysicsRangeError)
        assert_same_error(_rate(model), bad_angle, PhysicsRangeError)


def test_api_functions_match_arrays():
    """The API limit and the comparison match on arrays, including the exceedance flag."""
    assert_function_matches(erosion.api_erosional_velocity, [(1.0,), (1068.0,), (250.0,)])
    assert_same_error(erosion.api_erosional_velocity, [(1068.0,), (0.0,)], PhysicsRangeError)
    comparison = [(1.0, 2.0), (3.0, 2.0), (2.0, 2.0)]
    assert_function_matches(erosion.api_velocity_comparison, comparison)
    assert_same_error(erosion.api_velocity_comparison, [(1.0, 2.0), (1.0, 0.0)], PhysicsRangeError)


@pytest.mark.parametrize("model", ["DNV", "OKA", "TULSA"])
@pytest.mark.parametrize("cast", [float, int, np.float64])
def test_erosion_rate_returns_a_float(model, cast):
    """The outermost call gives a Python float whatever the numeric type of the inputs."""
    rate = erosion.erosion_rate(model, flow_rate=cast(1), rho_fluid=cast(1068), diameter=cast(1))
    assert type(rate) is float


@pytest.mark.parametrize("model", ["DNV", "OKA", "TULSA"])
def test_nan_input_passes_through_and_a_negative_flow_is_complex(model):
    """A NaN input gives NaN as before; only finite inputs with a negative flow are rejected."""
    nan = float("nan")
    assert math.isnan(erosion.erosion_rate(model, **(FLOW | {"flow_rate": nan})))
    assert math.isnan(erosion.erosion_rate(model, **(FLOW | {"rho_fluid": nan})))
    with pytest.raises(PhysicsRangeError, match="complex rate"):
        erosion.erosion_rate(model, **(FLOW | {"flow_rate": -0.04}))


def test_a_stopped_row_drops_the_complex_rate_error():
    """A negative flow behind a ``where`` on a stopped row does not fail the other rows."""

    @ops.physics
    def guarded(flow_rate, stopped):
        rate = erosion.erosion_rate("DNV", **(FLOW | {"flow_rate": flow_rate}))
        return ops.where(stopped > 0, 0.0, rate)

    rows = [(0.04, 0.0), (-0.04, 1.0), (0.01, 0.0), (float("nan"), 0.0)]
    assert_function_matches(guarded, rows)
    assert_same_error(guarded, [(0.04, 0.0), (-0.04, 0.0)], PhysicsRangeError)


def test_a_negative_integer_flow_is_the_complex_rate_error():
    """An integer argument behaves like its float: the complex rate raises the proper class."""
    with pytest.raises(PhysicsRangeError, match="complex rate"):
        erosion.erosion_rate("DNV", flow_rate=-1, rho_fluid=1000, diameter=1)
