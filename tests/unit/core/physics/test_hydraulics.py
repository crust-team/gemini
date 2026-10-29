"""Pipe friction, Beggs–Brill two-phase flow, path marching and radial inflow."""

import json
import math
from pathlib import Path
from types import SimpleNamespace

import pytest

from gemini.core.physics import geometry, hydraulics
from gemini.core.types.flows import Stream
from gemini.core.types.fluid import BRINE, Fluid
from gemini.errors import PhysicsRangeError, UnknownCorrelationError
from tests.unit.test_golden import assert_values

GOLDEN = json.loads((Path(__file__).parents[3] / "fixtures/golden_values.json").read_text())
FLUID_PROPERTIES = (1.976, 1000.0)
GAS = Fluid(gas_mass_fraction=0.01)


def _path(*diameters):
    """Return a vertical path of 100 m sections with the given internal diameters."""
    return geometry.PipePath(
        sections=[
            geometry.PipeSection(
                length=100, inclination=math.pi / 2, inner_diameter=d, roughness=2e-5
            )
            for d in diameters
        ]
    )


@pytest.mark.parametrize("role", ["production", "injection"])
def test_path_golden(role):
    """Path marching preserves every original section pressure and temperature."""
    case = GOLDEN["well_" + role]
    p = case["parameters"]
    u = case["inputs"]
    path = geometry.PipePath(
        sections=[
            geometry.PipeSection(length=length, inclination=a, inner_diameter=d, roughness=r)
            for length, a, d, r in zip(p["length"], p["angle"], p["diameter"], p["roughness"])
        ]
    )
    stream = SimpleNamespace(m_dot=u["flowrate"] * 1000, p=u["pressure"], T=u["temperature"])
    result = hydraulics.pipe_path_profile(
        path, stream, BRINE, u["direction"], 10, u["temperature_ambient"]
    )
    assert_values(
        dict(
            pressure_output=result.p_out,
            temperature_output=result.T_out,
            pressuredrop_fric_output=result.dp_fric,
            pressuredrop_grav_output=result.dp_grav,
            section_pressure_output=result.section_p,
            section_temperature_output=result.section_T,
        ),
        case["expected"],
    )


def test_darcy_and_beggs_brill_goldens():
    """Both pressure-drop correlations reproduce the original phase-0 cases."""
    assert hydraulics.darcy_weisbach_dp(*GOLDEN["darcy"]["inputs"]) == pytest.approx(
        GOLDEN["darcy"]["expected"], rel=1e-9
    )
    assert hydraulics.beggs_brill_dp(*GOLDEN["beggs"]["inputs"]) == pytest.approx(
        GOLDEN["beggs"]["expected"], rel=1e-9
    )


def test_darcy_friction_follows_the_flow_sign():
    """Reverse flow reverses friction; zero velocity leaves only gravity."""
    forward = hydraulics.darcy_weisbach_dp(2, 1000, 0.5, 1e-3, 0.1778, 2e-5, 100)
    reverse = hydraulics.darcy_weisbach_dp(-2, 1000, 0.5, 1e-3, 0.1778, 2e-5, 100)
    assert reverse == (-forward[0], forward[1])
    assert hydraulics.darcy_weisbach_dp(0, 1000, 0.5, 1e-3, 0.1778, 2e-5, 100) == (
        0.0,
        forward[1],
    )


@pytest.mark.parametrize(
    "us_l,inclination,diameter,expected",
    [
        (0.5, -0.1, 0.05, ("0x1.91c0499b9cdcfp+12", "-0x1.7e9094ec4ae5ap+16")),
        (0.5, 0.1, 0.05, ("0x1.91c0499b9cdcfp+12", "0x1.7e9094ec4ae5ap+16")),
        (0.5, -0.1, 0.1778, ("0x1.e1f2464fc2d34p+10", "-0x1.4e56f79e456d8p+16")),
        (0.5, 0.1, 0.1778, ("0x1.e1f1bef7430d7p+10", "0x1.4e603be43ea52p+16")),
        (0.0001, -0.1, 0.05, ("0x1.5e800bad3ce89p-8", "-0x1.a6b80ba0b55cap+15")),
        (0.0001, 0.1, 0.05, ("0x1.3748a32308d58p-8", "0x1.7e9094ec4ae5ap+16")),
        (0.05, -0.1, 0.05, ("0x1.df0f84de7a0adp+6", "-0x1.7e9094ec4ae5ap+16")),
        (0.05, 0.0, 0.05, ("0x1.df0f84de7a0adp+6", "0x0.0p+0")),
    ],
)
def test_beggs_brill_pinned_bits_in_every_regime(us_l, inclination, diameter, expected):
    """Distributed, intermittent, segregated and transition flow keep their original bits."""
    friction, gravity = hydraulics.beggs_brill_dp(
        0.0001, us_l, *FLUID_PROPERTIES, inclination, 21.29e-6, 1e-3, 0.0728, diameter, 2e-5, 100
    )
    assert (friction.hex(), gravity.hex()) == expected


def test_flow_regime_map_and_exact_boundaries():
    """The exact no-slip holdup 0.4 falls into the upper regime of the map."""
    assert hydraulics._flow_regime(0.005, 1.0)[0] == "segregated"
    assert hydraulics._flow_regime(0.2, 1e4)[0] == "distributed"
    assert hydraulics._flow_regime(0.01, 100.0)[0] == "distributed"
    assert hydraulics._flow_regime(0.4, 1.0)[0] == "intermittent"
    assert hydraulics._flow_regime(0.4, 1e4)[0] == "distributed"
    with pytest.raises(PhysicsRangeError, match="flow-regime map"):
        hydraulics._flow_regime(float("nan"), 1.0)


def test_beggs_brill_exact_boundary_no_longer_divides_by_zero():
    """No-slip holdup exactly 0.4 formerly matched no regime and raised ZeroDivisionError."""
    friction, gravity = hydraulics.beggs_brill_dp(
        0.6, 0.4, *FLUID_PROPERTIES, math.pi / 2, 21.29e-6, 1e-3, 0.0728, 0.2, 2e-5, 100
    )
    assert friction > 0 and gravity > 0


def test_beggs_brill_rejects_zero_holdup_and_missing_liquid():
    """Steep downhill flow can clamp the holdup to zero; pure gas has no liquid number."""
    with pytest.raises(PhysicsRangeError, match="holdup = 0"):
        hydraulics.beggs_brill_dp(
            0.5, 0.05, *FLUID_PROPERTIES, -math.pi / 4, 21.29e-6, 1e-3, 0.0728, 0.1778, 2e-5, 100
        )
    with pytest.raises(PhysicsRangeError, match="us_l = 0"):
        hydraulics.beggs_brill_dp(
            0.5, 0, *FLUID_PROPERTIES, 0.7, 21.29e-6, 1e-3, 0.0728, 0.1778, 2e-5, 100
        )


def test_two_phase_reverse_flow_reverses_friction():
    """Negative two-phase flow formerly took the logarithm of a negative Reynolds number."""
    path = _path(0.18, 0.18)
    forward = Stream(m_dot=40, T=350, p=20e5, fluid=GAS)
    reverse = Stream(m_dot=-40, T=350, p=20e5, fluid=GAS)
    ahead = hydraulics.pipe_path_profile(path, forward, GAS, "down", 0, 300)
    back = hydraulics.pipe_path_profile(path, reverse, GAS, "down", 0, 300)
    assert back.dp_fric == pytest.approx(-ahead.dp_fric)
    assert back.dp_grav == pytest.approx(ahead.dp_grav)


def test_zero_flow_unknown_correlation_and_direction():
    """Preserve DPDT zero-flow behavior and reject unknown correlations and directions."""
    path = _path(0.18)
    stream = Stream(m_dot=0, p=1e6, T=350)
    result = hydraulics.pipe_path_profile(path, stream, BRINE, "up", 10, 290)
    assert result.p_out == stream.p and result.T_out == stream.T
    assert result.dp_fric == result.dp_grav == 0
    assert hydraulics.pipe_path_profile(path, stream, BRINE, " Up ", 10, 290) == result
    with pytest.raises(UnknownCorrelationError, match="'unknown'"):
        hydraulics.pipe_path_profile(path, stream, BRINE, "up", 10, 290, correlation="unknown")
    with pytest.raises(ValueError, match="direction = 'sideways'"):
        hydraulics.pipe_path_profile(path, stream, BRINE, "sideways", 10, 290)


def test_corrosion_profile_pairs_sections_in_traversal_order():
    """A capitalised direction formerly paired downward results with reversed sections."""
    path = _path(0.1, 0.3)
    stream = Stream(m_dot=40, T=350, p=50e5)
    chemistry = {"co2_fraction": 0.05}
    lower = hydraulics.corrosion_profile(path, stream, BRINE, "down", 0, 350, chemistry, "DLD")
    upper = hydraulics.corrosion_profile(path, stream, BRINE, "Down", 0, 350, chemistry, "DLD")
    assert upper == lower
    assert lower[0] != lower[1]


def test_erosion_check_compares_each_section():
    """Narrow sections run faster and raise the API alarm first."""
    result = hydraulics.erosion_check(_path(0.02, 0.3), Stream(m_dot=40, T=350, p=50e5), BRINE)
    assert result["velocity"][0] > result["limit"] > result["velocity"][1]
    assert result["alarm"] is True
    assert [s["exceeds_api_limit"] for s in result["sections"]] == [True, False]


def test_radial_pressure_drops_and_hydrostatics():
    """Radial Darcy and skin drops scale with flow; nonpositive geometry is rejected."""
    flow_dp, skin_dp = hydraulics.radial_pressure_drops(0.04, 6.5e-4, 1e-11, 45, 1000, 0.0765, 2)
    assert flow_dp == pytest.approx(
        0.04 * 6.5e-4 * math.log(1000 / 0.0765) / (2 * math.pi * 1e-11 * 45)
    )
    assert skin_dp == pytest.approx(0.04 * 6.5e-4 * 2 / (2 * math.pi * 1e-11 * 45))
    with pytest.raises(PhysicsRangeError, match="thickness = 0"):
        hydraulics.radial_pressure_drops(0.04, 6.5e-4, 1e-11, 0, 1000, 0.0765, 2)
    assert hydraulics.hydrostatic_dp(1000, 10) == pytest.approx(98100)
