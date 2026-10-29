"""Desander pressure loss, sand removal and limits."""

import pytest

import gemini as gm
from gemini.core.modules.balance import energy_balance, mass_balance
from gemini.core.modules.treatment import Desander
from gemini.core.types.flows import Stream

INLET = Stream(m_dot=20, T=350, p=1e6)


def desander():
    """Return a desander rated 1 bar at 40 kg/s that removes 90 % of the sand."""
    return Desander().update_params(separation_efficiency=0.9, dp_nominal=1e5, m_dot_nominal=40)


def test_hand_computed_removal_and_loss():
    """Quadratic loss and removal from the liquid volume flow, with mg/l accepted."""
    module = desander()
    result = module(inlet=INLET, sand_concentration="50 mg/l")
    out = result.outputs
    assert out.pressure_drop == 25000
    assert result.outlets.outlet == INLET.with_(p=1e6 - 25000)
    assert out.sand_removal_rate == pytest.approx(0.9 * 0.05 * 0.02)
    assert out.residual_sand_concentration == pytest.approx(0.005)
    assert mass_balance(module, result)["residual"] == 0
    assert energy_balance(module, result)["relative_residual"] < 1e-12


def test_limits():
    """Zero flow removes nothing; reverse flow and a loss above inlet pressure raise."""
    module = desander()
    stopped = module(inlet=INLET.with_(m_dot=0), sand_concentration=0.05).outputs
    assert stopped.pressure_drop == 0 and stopped.sand_removal_rate == 0
    with pytest.raises(gm.errors.PhysicsRangeError, match="inlet.m_dot"):
        module(inlet=INLET.with_(m_dot=-1), sand_concentration=0.05)
    with pytest.raises(gm.errors.PhysicsRangeError, match="pressure_drop"):
        module(inlet=INLET.with_(m_dot=200, p=2e5), sand_concentration=0.05)
    with pytest.raises(gm.errors.DeclarationError):
        module(inlet=INLET, sand_concentration=-1)
    with pytest.raises(gm.errors.MissingValueError):
        Desander()(inlet=INLET, sand_concentration=0.05)
