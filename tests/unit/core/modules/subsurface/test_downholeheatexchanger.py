"""Deep coaxial downhole heat exchanger in a linear geothermal gradient."""

import math

import pytest

import gemini as gm
from gemini.core.modules import energy_balance, mass_balance
from gemini.core.modules.subsurface import DownholeHeatExchanger
from gemini.core.types import Stream

INLET = Stream(m_dot=5, T=303.15, p=3e5)
CP = 4217.4


def exchanger():
    """Return a 2.5 km exchanger after one year of operation."""
    return DownholeHeatExchanger().update_params(
        depth="2500 m",
        surface_temperature="10 degC",
        geothermal_gradient="30 K/km",
        rock_conductivity=2.5,
        rock_diffusivity=1e-6,
        borehole_radius=0.1,
        borehole_resistance=0.05,
        operating_time=3.15e7,
    )


def hand_outlet(m_dot, inlet_T):
    """Return Ramey's bottom-hole temperature [K] computed by hand."""
    function = math.log(2 * math.sqrt(1e-6 * 3.15e7) / 0.1) - 0.5772156649015329 / 2
    relaxation = m_dot * CP * (0.05 + function / (2 * math.pi * 2.5))
    rock = 283.15 + 0.03 * 2500
    decay = math.exp(-2500 / relaxation)
    return rock - 0.03 * relaxation + (inlet_T - 283.15 + 0.03 * relaxation) * decay


def test_outlet_follows_ramey_and_the_balance_closes():
    """The fluid leaves at Ramey's bottom-hole temperature; extracted heat closes the audit."""
    module = exchanger()
    assert module.geothermal_gradient == pytest.approx(0.03)
    result = module(inlet=INLET)
    out = result.outputs
    assert out.outlet_T == pytest.approx(hand_outlet(5, 303.15), rel=1e-12)
    assert out.heat_extraction_rate == pytest.approx(5 * CP * (out.outlet_T - 303.15))
    assert out.heat_absorbed == out.heat_extraction_rate > 0 and out.heat_loss == 0
    assert result.outlets.outlet.p == INLET.p and result.outlets.outlet.m_dot == 5
    assert energy_balance(module, result)["relative_residual"] < 1e-12
    assert mass_balance(module, result)["residual"] == 0


def test_flow_limits():
    """Slow flow approaches the bottom-hole rock temperature; zero flow passes unchanged."""
    module = exchanger()
    slow = module(inlet=INLET.with_(m_dot=0.01)).outputs.outlet_T
    assert slow == pytest.approx(hand_outlet(0.01, 303.15)) and 0 < 283.15 + 75 - slow < 0.5
    still = module(inlet=INLET.with_(m_dot=0))
    assert still.outlets.outlet == INLET.with_(m_dot=0)
    assert still.outputs.heat_extraction_rate == 0
    with pytest.raises(gm.errors.PhysicsRangeError, match="inlet.m_dot = -1"):
        module(inlet=INLET.with_(m_dot=-1))


def test_hot_inlet_heats_the_rock():
    """An inlet hotter than the rock everywhere loses heat to it as heat_loss."""
    module = exchanger()
    result = module(inlet=INLET.with_(T=400))
    assert result.outputs.heat_extraction_rate < 0 and result.outputs.heat_absorbed == 0
    assert result.outputs.heat_loss == -result.outputs.heat_extraction_rate
    assert energy_balance(module, result)["relative_residual"] < 1e-12


def test_short_operating_time_is_bad_design_data():
    """Ramey's long-time function needs alpha t / r**2 >= 25."""
    module = exchanger().update_params(operating_time=3600)
    with pytest.raises(gm.errors.ConfigurationError, match="operating_time rejected"):
        module(inlet=INLET)
