"""Dry and wet coolers: approach limits, capacity, fan power, evaporation and closure."""

import pytest

from gemini.errors import PhysicsError, ValidationError
from gemini.modules._utils.balance import energy_balance, mass_balance
from gemini.modules.exchangers import Cooler
from gemini.types.flows import Stream
from tests.fixtures.equivalence import assert_module_matches
from tests.fixtures.errors import raises

CP = 4217.4
HOT = Stream(m_dot=20, T=313.15, p=3e5)


def cooler(cooler_type, **params):
    """Return a 2 MW cooler with a 5 K approach and 2 % specific fan power."""
    design = dict(cooler_type=cooler_type, capacity=2e6, approach=5, specific_fan_power=0.02)
    return Cooler().update_params(**(design | params))


def test_dry_cooler_approach_limit_and_closure():
    """A dry cooler stops at dry bulb plus approach; fan power leaves as heat to the air."""
    unit = cooler("dry")
    result = unit(fluid_in=HOT, temperature_setpoint=293.15, ambient_temperature=298.15)
    out = result.outputs
    assert out.fluid_out_T == pytest.approx(303.15)
    assert out.duty == pytest.approx(20 * CP * 10)
    assert out.electricity == pytest.approx(0.02 * out.duty)
    assert out.heat_loss == pytest.approx(1.02 * out.duty)
    assert out.evaporation_rate == 0 and not out.is_capped
    assert result.outlets.fluid_out.m_dot == HOT.m_dot and result.outlets.fluid_out.p == HOT.p
    assert energy_balance(unit, result)["relative_residual"] < 1e-12
    assert mass_balance(unit, result)["residual"] == 0
    warm = unit(fluid_in=HOT, temperature_setpoint=308.15, ambient_temperature=280).outputs
    assert warm.fluid_out_T == pytest.approx(308.15)


def test_wet_cooler_uses_wet_bulb_and_reports_evaporation():
    """A wet cooler reaches wet bulb plus approach and evaporates duty / latent heat."""
    unit = cooler("wet")
    result = unit(
        fluid_in=HOT,
        temperature_setpoint=280,
        ambient_temperature=303.15,
        wet_bulb_temperature=295.15,
    )
    out = result.outputs
    assert out.fluid_out_T == pytest.approx(300.15)
    assert out.evaporation_rate == pytest.approx(20 * CP * 13 / 2.43e6)
    assert result.outlets.fluid_out.m_dot == HOT.m_dot
    assert energy_balance(unit, result)["relative_residual"] < 1e-12


def test_capacity_cap_and_no_cooling():
    """Capacity caps the duty; an inlet below the reachable outlet or no flow rejects nothing."""
    out = cooler("dry", capacity=5e5)(
        fluid_in=HOT, temperature_setpoint=280, ambient_temperature=280
    ).outputs
    assert out.is_capped and out.duty == 5e5
    assert out.fluid_out_T == pytest.approx(HOT.T - 5e5 / (20 * CP))
    for stream, ambient in ((HOT, 310), (HOT.with_(m_dot=0), 280)):
        result = cooler("dry")(
            fluid_in=stream, temperature_setpoint=280, ambient_temperature=ambient
        )
        assert result.outputs.duty == result.outputs.electricity == 0
        assert result.outlets.fluid_out.T == HOT.T


def test_invalid_inputs_raise():
    """A wet cooler needs a wet bulb at or below the dry bulb; flow must not be reversed."""
    with raises(ValidationError, "invalid_design", match="wet_bulb_temperature = None"):
        cooler("wet")(fluid_in=HOT, temperature_setpoint=290, ambient_temperature=300)
    with pytest.raises(PhysicsError, match="wet_bulb_temperature = 305"):
        cooler("wet")(
            fluid_in=HOT,
            temperature_setpoint=290,
            ambient_temperature=300,
            wet_bulb_temperature=305,
        )
    with pytest.raises(PhysicsError, match="fluid_in.m_dot = -1"):
        cooler("dry")(
            fluid_in=HOT.with_(m_dot=-1), temperature_setpoint=290, ambient_temperature=300
        )


@pytest.mark.parametrize("cooler_type", ["dry", "wet"])
def test_traced_call_matches_one_call_per_row(cooler_type):
    """Approach-limited, capped, warm-enough and stopped rows trace and equal per-row calls."""
    unit = cooler(cooler_type)
    rows = [
        dict(
            fluid_in=Stream(m_dot=m_dot, T=T, p=3e5),
            temperature_setpoint=setpoint,
            ambient_temperature=298.15,
            wet_bulb_temperature=wet_bulb,
        )
        for m_dot, T, setpoint, wet_bulb in [
            (20, 313.15, 293.15, 290.0),
            (20, 313.15, 308.15, 290.0),
            (60, 340.0, 293.15, 295.0),
            (0, 313.15, 293.15, 290.0),
            (20, 300.0, 310.0, 298.15),
        ]
    ]
    assert_module_matches(unit, rows)
