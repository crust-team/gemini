"""ORC Lorenz-cycle power, first-law closure, capacity bypass, ambient and idle limits."""

import math

import pytest

import gemini as gm
from gemini.modules import energy_balance, mass_balance
from gemini.modules.power import ORC
from gemini.types import Stream
from tests.fixtures.equivalence import assert_module_matches

BRINE = Stream(m_dot=100, T=423.15, p=10e5)
"""Brine at 150 degC and 100 kg/s."""


def orc(**changes):
    """Return an air-cooled ORC with a 70 degC reinjection limit."""
    params = dict(
        minimum_brine_outlet_temperature="70 degC",
        pinch=5,
        fraction_of_carnot=0.5,
        condenser_approach=15,
        parasitic_fraction=0.15,
        capacity="5 MW",
    )
    return ORC().update_params(**(params | changes))


def test_hand_calculated_lorenz_power():
    """Brine 150 -> 70 degC, T_c = 15 + 15 degC: W = 0.5 m cp ((T_a - T_b) - T_c ln(T_a/T_b))."""
    out = orc()(brine_in=BRINE, ambient_temperature="15 degC").outputs
    heat = 100 * 4217.4 * 80
    gross = 0.5 * 100 * 4217.4 * (80 - 303.15 * math.log(418.15 / 338.15))
    assert out.heat_input == pytest.approx(heat, rel=1e-12)
    assert out.gross_power == pytest.approx(gross, rel=1e-12)
    assert out.parasitic_power == pytest.approx(0.15 * gross, rel=1e-12)
    assert out.electricity_generated == pytest.approx(0.85 * gross, rel=1e-12)
    assert out.condenser_duty == pytest.approx(heat - gross, rel=1e-12)
    assert out.thermal_efficiency == pytest.approx(0.85 * gross / heat, rel=1e-12)
    assert out.brine_out_T == pytest.approx(343.15) and out.condensing_temperature == 303.15
    assert not out.is_capped


def test_first_law_and_mass_closure():
    """Heat input = net power + heat loss, audited with the brine's cp."""
    module = orc()
    result = module(brine_in=BRINE, ambient_temperature=288.15)
    out = result.outputs
    assert out.heat_input == pytest.approx(out.gross_power + out.condenser_duty, rel=1e-12)
    assert energy_balance(module, result)["relative_residual"] < 1e-12
    assert mass_balance(module, result)["residual"] == 0


def test_capacity_bypasses_brine_at_constant_cycle_efficiency():
    """A 1 MW cap processes part of the brine; the mixed outlet is warmer."""
    full = orc()(brine_in=BRINE, ambient_temperature=288.15).outputs
    module = orc(capacity="1 MW")
    result = module(brine_in=BRINE, ambient_temperature=288.15)
    out = result.outputs
    assert out.is_capped and out.gross_power == pytest.approx(1e6, rel=1e-12)
    assert 343.15 < out.brine_out_T < 423.15
    assert out.thermal_efficiency == pytest.approx(full.thermal_efficiency, rel=1e-12)
    assert energy_balance(module, result)["relative_residual"] < 1e-12


def test_hot_ambient_raises_condensing_and_outlet_temperatures():
    """At 55 degC ambient the pinch above T_c sets the brine outlet; power falls."""
    cool = orc()(brine_in=BRINE, ambient_temperature="15 degC").outputs
    hot = orc()(brine_in=BRINE, ambient_temperature="55 degC").outputs
    assert hot.brine_out_T == pytest.approx(273.15 + 55 + 15 + 5)
    assert hot.electricity_generated < cool.electricity_generated


def test_idle_zero_flow_and_reverse_flow():
    """Brine below the outlet limit or no flow gives no power; reverse flow raises."""
    cold = BRINE.with_(T=340)
    result = orc()(brine_in=cold, ambient_temperature=288.15)
    assert result.outputs.electricity_generated == 0 and result.outputs.thermal_efficiency is None
    assert result.outlets.brine_out.T == 340
    stopped = orc()(brine_in=BRINE.with_(m_dot=0), ambient_temperature=288.15).outputs
    assert stopped.heat_input == 0 and stopped.gross_power == 0 and not stopped.is_capped
    with pytest.raises(gm.errors.PhysicsRangeError, match="brine_in.m_dot = -1"):
        orc()(brine_in=BRINE.with_(m_dot=-1), ambient_temperature=288.15)


def test_traced_call_matches_one_call_per_row():
    """Running, capped, idle (inlet too cold) and stopped rows trace and equal one call per row."""
    rows = [
        dict(brine_in=Stream(m_dot=m_dot, T=T, p=10e5), ambient_temperature=ambient)
        for m_dot, T, ambient in [
            (100.0, 423.15, 288.15),
            (400.0, 423.15, 288.15),
            (100.0, 330.0, 288.15),
            (0.0, 423.15, 288.15),
            (50.0, 400.0, 303.15),
        ]
    ]
    assert_module_matches(orc(), rows)
