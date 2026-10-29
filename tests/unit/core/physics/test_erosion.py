"""Erosion rate correlations, API velocity limit and their input domain."""

import json
import math
from pathlib import Path

import pytest

from gemini.core.physics import erosion, units
from gemini.errors import PhysicsRangeError, UnknownCorrelationError

GOLDEN = json.loads((Path(__file__).parents[3] / "fixtures/golden_values.json").read_text())
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
