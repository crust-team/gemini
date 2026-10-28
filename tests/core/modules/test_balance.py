"""Typed energy reporting, nonduplicated aggregation and conservation diagnostics."""

import pytest

from gemini.core.modules.balance import collect_flows, energy_balance, mass_balance
from gemini.core.modules.heat.boiler import Boiler
from gemini.core.modules.module import Sequential
from gemini.core.modules.pumps.injectionpump import InjectionPump
from gemini.core.types.flows import PowerFlow, Stream


@pytest.mark.parametrize("fuel", ["electric", "gas"])
def test_boiler_balance(fuel):
    """Electric and gas boilers conserve total energy, including conversion losses."""
    boiler = Boiler(dict(fuel=fuel, capacity=1e6, efficiency=0.9))
    inlet = Stream(m_dot=10, T=300, p=1e6)
    result = boiler(dict(setpoint_T=320), inlet=inlet)
    assert mass_balance(boiler, result)["residual"] == 0
    assert energy_balance(boiler, result)["relative_residual"] < 1e-12
    assert collect_flows(result)["electricity" if fuel == "electric" else "fuel"] > 0
    with pytest.raises(TypeError, match="requires Stream"):
        boiler(dict(setpoint_T=320), inlet=PowerFlow(P=1))


def test_collect_once_and_unresolved_pump_work():
    """Retained result trees expose the legacy isothermal pump's missing energy allocation."""
    pump = InjectionPump(dict(efficiency=0.8))
    chain = Sequential({"pump": pump})
    result = chain({"pump": {"discharge_pressure": 2e6}}, suction=Stream(m_dot=10, T=300, p=1e6))
    flows = collect_flows(result)
    assert flows["electricity"] == 12500
    balance = energy_balance(chain, result)
    assert balance["residual"] == pytest.approx(12500)
    assert balance["unresolved_power"] == pytest.approx(12500)
    assert balance["relative_thermal_residual"] < 1e-12
    assert mass_balance(chain, result)["residual"] == 0
    chain({"pump": {"discharge_pressure": 3e6}}, suction=Stream(m_dot=10, T=300, p=1e6))
    assert collect_flows(result) == flows
