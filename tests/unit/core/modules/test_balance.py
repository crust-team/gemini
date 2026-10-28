"""Typed energy reporting and conservation diagnostics."""

import pytest

from gemini.core.modules.balance import collect_flows, energy_balance, mass_balance
from gemini.core.modules.heat import Boiler
from gemini.core.modules.pumps import ESP, InjectionPump
from gemini.core.types import Stream


@pytest.mark.parametrize("fuel", ["electric", "gas"])
def test_boiler_balance(fuel):
    """Electric and gas boilers conserve total modeled energy."""
    boiler = Boiler(fuel_type=fuel, capacity=1e6, efficiency=0.9)
    result = boiler(inlet=Stream(m_dot=10, T=300, p=1e6), setpoint_T=320)
    assert mass_balance(boiler, result)["residual"] == 0
    assert energy_balance(boiler, result)["relative_residual"] < 1e-12
    assert collect_flows(result)["electricity" if fuel == "electric" else "fuel"] > 0


def test_unresolved_pump_work():
    """Isothermal pump electricity remains explicit unresolved work."""
    pump = InjectionPump(efficiency=0.8)
    result = pump(suction=Stream(m_dot=10, T=300, p=1e6), pressure_setpoint=2e6)
    balance = energy_balance(pump, result)
    assert balance["unresolved_power"] == pytest.approx(result.outputs.power)
    assert balance["relative_thermal_residual"] < 1e-12


def test_esp_motor_efficiency_does_not_change_shaft_power():
    """Motor efficiency changes grid draw while shaft prediction stays fixed."""
    pump = ESP(
        no_stages=10,
        head_coeff=[10, 0, 0, 0, 0, 0],
        power_coeff=[1, 0, 0, 0, 0, 0],
    )
    inlet = Stream(m_dot=30, T=300, p=1e6)
    first = pump(frequency=60, suction=inlet)
    pump.motor_efficiency = 0.5
    second = pump(frequency=60, suction=inlet)
    assert second.outputs.power == first.outputs.power
    assert second.outputs.electricity == 2 * first.outputs.power
