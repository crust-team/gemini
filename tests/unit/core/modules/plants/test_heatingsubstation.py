"""Heating substation: building loop closure, demand caps, limits and balances."""

import math

import pytest

import gemini as gm
from gemini.core.modules import energy_balance, mass_balance
from gemini.core.modules.plants import HeatingSubstation
from gemini.core.types import Stream

CP = 4217.4
NETWORK = Stream(m_dot=2.0, T=348.15, p=6e5)


def counterflow_effectiveness(ua, c_min, c_max):
    """Return the counterflow effectiveness [-] (Incropera et al., effectiveness-NTU)."""
    ntu, ratio = ua / c_min, c_min / c_max
    decay = math.exp(-ntu * (1 - ratio))
    return (1 - decay) / (1 - ratio * decay)


def test_met_demand_closes_the_building_loop(plants):
    """With the demand met the return follows from e C_min (T_network - T_return) = Q."""
    substation = plants["heating_substation"](HeatingSubstation())
    result = substation(network_in=NETWORK)
    out = result.outputs
    effectiveness = counterflow_effectiveness(2e4, 2 * CP, 3 * CP)
    assert out.heat_supplied == pytest.approx(1.5e5, rel=1e-12)
    assert out.duty == pytest.approx(1.5e5, rel=1e-9)
    assert not out.is_unmet and out.unmet_demand == pytest.approx(0, abs=1e-6)
    assert out.network_out_T == pytest.approx(348.15 - 1.5e5 / (2 * CP), rel=1e-12)
    expected_return = 348.15 - 1.5e5 / (effectiveness * 2 * CP)
    assert out.building_return_T == pytest.approx(expected_return, abs=1e-8)
    assert out.building_supply_T == pytest.approx(expected_return + 1.5e5 / (3 * CP), abs=1e-8)
    valve = result.children["valve"]
    assert out.valve_pressure_drop == valve.outputs.pressure_drop > 0
    assert result.outlets.network_out.p == pytest.approx(6e5 - out.valve_pressure_drop - 2e4)
    assert energy_balance(substation, result)["relative_residual"] < 1e-12
    assert mass_balance(substation, result)["residual"] == 0
    assert list(result.leaves()) == ["valve", "heat_exchanger", "consumer"]


def test_large_demand_is_capped_at_the_return_floor(plants):
    """Beyond the exchanger's reach the return sits at the floor and the rest is unmet."""
    substation = plants["heating_substation"](HeatingSubstation(), demand=5e5)
    out = substation(network_in=NETWORK).outputs
    effectiveness = counterflow_effectiveness(2e4, 2 * CP, 3 * CP)
    available = effectiveness * 2 * CP * (348.15 - 303.15)
    assert out.building_return_T == pytest.approx(303.15, abs=1e-8)
    assert out.heat_supplied == pytest.approx(available, rel=1e-9)
    assert out.is_unmet and out.unmet_demand == pytest.approx(5e5 - available, rel=1e-9)


def test_stopped_or_cold_network_delivers_nothing(plants):
    """No network flow, or a supply below the return floor, leaves the demand unmet."""
    substation = plants["heating_substation"](HeatingSubstation())
    stopped = substation(network_in=NETWORK.with_(m_dot=0.0)).outputs
    assert stopped.heat_supplied == 0 and stopped.unmet_demand == 1.5e5
    assert stopped.valve_pressure_drop == 0 and stopped.network_out_T == 348.15
    cold = substation(network_in=NETWORK.with_(T=300.15)).outputs
    assert cold.heat_supplied == 0 and cold.building_return_T == 300.15


def test_invalid_inputs_raise(plants):
    """A closed valve with flow and reverse flow raise; missing data names the parameters."""
    substation = plants["heating_substation"](HeatingSubstation())
    substation.valve.opening = 0
    with pytest.raises(gm.errors.PhysicsRangeError, match="closed valve"):
        substation(network_in=NETWORK)
    substation.valve.opening = 0.8
    with pytest.raises(gm.errors.PhysicsRangeError):
        substation(network_in=NETWORK.with_(m_dot=-1.0))
    with pytest.raises(gm.errors.MissingValueError, match="building_flow"):
        HeatingSubstation()(network_in=NETWORK)
