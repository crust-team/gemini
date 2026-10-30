"""Flash separator split, IF97 enthalpy closure, subcooled inlet and domain limits."""

import pytest

import gemini as gm
from gemini.modules import mass_balance
from gemini.modules.power import Separator
from gemini.physics import steam
from gemini.types import STEAM, Stream
from tests.fixtures.equivalence import assert_module_matches

GEOFLUID = Stream(m_dot=100, T=523.15, p=40e5)
"""Liquid at 250 degC and 40 bar, a typical liquid-dominated wellhead feed."""


def test_flash_split_matches_steam_tables():
    """250 degC liquid flashed to 6 bar: x = (1085.8 - 670.4) / 2085.9 = 0.199 (steam tables)."""
    result = Separator()(inlet=GEOFLUID, pressure_setpoint="6 bar")
    out, liquid, gas = result.outputs, result.outlets.liquid, result.outlets.gas
    assert out.steam_fraction == pytest.approx((1085.8 - 670.4) / 2085.9, abs=2e-4)
    assert out.saturation_temperature == pytest.approx(431.98, abs=0.01)
    assert out.steam_mass_flow == gas.m_dot == pytest.approx(100 * out.steam_fraction)
    assert gas.fluid == STEAM and liquid.fluid == GEOFLUID.fluid
    assert liquid.T == gas.T == out.saturation_temperature
    assert liquid.p == gas.p == 6e5
    assert mass_balance(Separator(), result)["residual"] == 0


def test_closed_in_if97_enthalpies():
    """Closure: m h_in = m_gas h_g + m_liquid h_f; the cp*T audit cannot show latent heat."""
    result = Separator()(inlet=GEOFLUID, pressure_setpoint=6e5)
    saturation = steam.saturation_properties(6e5)
    incoming = GEOFLUID.m_dot * steam.liquid_enthalpy(GEOFLUID.p, GEOFLUID.T)
    outgoing = (
        result.outlets.gas.m_dot * saturation.vapour_enthalpy
        + result.outlets.liquid.m_dot * saturation.liquid_enthalpy
    )
    assert outgoing == pytest.approx(incoming, rel=1e-12)


def test_inlet_below_its_saturation_pressure_uses_the_liquid_enthalpy():
    """A wellhead stream already below saturation is the liquid at its temperature."""
    flashing = GEOFLUID.with_(p=8e5)
    result = Separator()(inlet=flashing, pressure_setpoint=6e5)
    enthalpy = steam.liquid_enthalpy(steam.saturation_pressure(523.15), 523.15)
    assert result.outputs.steam_fraction == pytest.approx(steam.flash_fraction(enthalpy, 6e5))


def test_subcooled_and_zero_flow():
    """A subcooled inlet passes as liquid at its temperature; zero flow splits nothing."""
    subcooled = Stream(m_dot=50, T=393.15, p=10e5)
    result = Separator()(inlet=subcooled, pressure_setpoint=6e5)
    assert result.outputs.steam_fraction == 0 and result.outlets.gas.m_dot == 0
    assert result.outlets.liquid.T == 393.15 and result.outlets.liquid.m_dot == 50
    stopped = Separator()(inlet=GEOFLUID.with_(m_dot=0), pressure_setpoint=6e5)
    assert stopped.outputs.steam_mass_flow == 0 and stopped.outlets.liquid.m_dot == 0
    assert stopped.outputs.steam_fraction > 0


def test_invalid_inlets_and_setpoints_raise():
    """Reverse flow, a steam inlet, a setpoint above the inlet and a supercritical feed."""
    separator = Separator()
    cases = [
        (GEOFLUID.with_(m_dot=-1), 6e5),
        (GEOFLUID.with_(fluid=STEAM), 6e5),
        (GEOFLUID, 50e5),
        (GEOFLUID.with_(T=650, p=250e5), 6e5),
    ]
    for inlet, setpoint in cases:
        with pytest.raises(gm.errors.PhysicsRangeError):
            separator(inlet=inlet, pressure_setpoint=setpoint)
    with pytest.raises(gm.errors.PhysicsRangeError, match="separator: pressure_setpoint"):
        separator(inlet=GEOFLUID, pressure_setpoint=50e5)


def test_traced_call_matches_one_call_per_row():
    """Flashing and subcooled rows at several setpoints trace and equal one call per row."""
    rows = [
        dict(inlet=Stream(m_dot=m_dot, T=T, p=p), pressure_setpoint=setpoint)
        for m_dot, T, p, setpoint in [
            (100.0, 523.15, 40e5, 6e5),
            (50.0, 523.15, 8e5, 6e5),
            (80.0, 400.0, 20e5, 5e5),
            (0.0, 500.0, 30e5, 2e5),
        ]
    ]
    assert_module_matches(Separator(), rows)
