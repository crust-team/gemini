"""Typed energy reporting and conservation diagnostics."""

import pytest

from gemini.core.modules import Module
from gemini.core.modules.balance import collect_flows, energy_balance, mass_balance
from gemini.core.modules.heat import Boiler
from gemini.core.modules.pumps import ESP, InjectionPump
from gemini.core.types import Inlet, Outlet, Output, Power, Stream


class Radiator(Module):
    """Deliver a fixed share of the stream's heat to a consumer and lose a little."""

    def __init__(self):
        """Declare the ports and the energy outputs."""
        super().__init__()

        # Inlets
        self.supply_in = Inlet(Stream)

        # Outputs
        self.heat_supplied = Output(Power)
        self.heat_loss = Output(Power)

        # Outlets
        self.return_out = Outlet(Stream)

    def forward(self, inlets):
        """Cool the stream by 10 K."""

        # Outlets
        return_out = inlets.supply_in.with_(T=inlets.supply_in.T - 10)

        outlets = dict(return_out=return_out)
        return outlets

    def _compute_outputs(self, inlets, outlets):
        released = inlets.supply_in.m_dot * 4217.4 * 10
        self.heat_supplied = 0.9 * released
        self.heat_loss = 0.1 * released


@pytest.mark.parametrize("fuel", ["electric", "gas"])
def test_boiler_balance(fuel):
    """Electric and gas boilers conserve total modeled energy."""
    boiler = Boiler().update_params(fuel_type=fuel, capacity=1e6, efficiency=0.9)
    result = boiler(inlet=Stream(m_dot=10, T=300, p=1e6), temperature_setpoint=320)
    assert mass_balance(boiler, result)["residual"] == 0
    assert energy_balance(boiler, result)["relative_residual"] < 1e-12
    assert collect_flows(result)["electricity" if fuel == "electric" else "fuel"] > 0


def test_unresolved_pump_work():
    """Isothermal pump electricity remains explicit unresolved work."""
    pump = InjectionPump().update_params(efficiency=0.8)
    result = pump(suction=Stream(m_dot=10, T=300, p=1e6), pressure_setpoint=2e6)
    balance = energy_balance(pump, result)
    assert balance["unresolved_power"] == pytest.approx(result.outputs.power)
    assert balance["relative_thermal_residual"] < 1e-12


def test_esp_motor_efficiency_does_not_change_shaft_power():
    """Motor efficiency changes grid draw while shaft prediction stays fixed."""
    pump = ESP().update_params(
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


def test_heat_supplied_to_a_consumer_closes_the_balance():
    """Heat delivered across the plant boundary is an energy outflow, not a residual."""
    radiator = Radiator()
    result = radiator(supply_in=Stream(m_dot=2, T=350, p=1e6))
    balance = energy_balance(radiator, result)
    assert balance["heat_supplied"] == pytest.approx(0.9 * 2 * 4217.4 * 10)
    assert balance["relative_residual"] < 1e-12
