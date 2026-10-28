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


def test_esp_reports_motor_efficiency_without_changing_shaft_power():
    """Motor efficiency changes grid draw while shaft power and hydraulic predictions stay fixed."""
    from gemini.core.modules.pumps.esp import ESP

    params = dict(no_stages=10, head_coeff=[10, 0, 0, 0, 0, 0], power_coeff=[1, 0, 0, 0, 0, 0])
    pump = ESP(params)
    inlet = Stream(m_dot=30, T=300, p=1e6)
    first = pump(dict(frequency=60), suction=inlet)
    assert first.streams["electricity"].P == first.outputs.power
    pump.update_params(motor_efficiency=0.5)
    second = pump(dict(frequency=60), suction=inlet)
    assert second.outputs == first.outputs
    assert second.streams["electricity"].P == 2 * first.outputs.power


def test_every_equipment_mass_and_modeled_thermal_balance():
    """Each declared equipment model conserves mass and its modeled thermal transfers."""
    from tests.unit.core.modules.test_contracts import example_modules

    for module in example_modules():
        inputs = (
            {"frequency": 60}
            if module.name == "esp"
            else (
                {"discharge_pressure": 2.1e7}
                if module.name == "injectionpump"
                else (
                    {"m_dot": 40}
                    if module.name == "production_reservoir"
                    else {"setpoint_T": 360} if module.name == "boiler" else {}
                )
            )
        )
        inlets = {
            port: Stream(m_dot=40, T=300 if port == "cold_in" else 350, p=2e7, fluid=module.fluid)
            for port in module.inlets
        }
        result = module(inputs, inlets)
        assert mass_balance(module, result)["relative_residual"] < 1e-6, module.name
        balance = energy_balance(module, result)
        assert balance["relative_thermal_residual"] < 1e-6, module.name
        if module.category != "pumps":
            assert balance["relative_residual"] < 1e-6, module.name
