"""Typed energy reporting and conservation diagnostics."""

import numpy as np
import pytest

from gemini.modules import Module
from gemini.modules.balance import collect_flows, emissions, energy_balance, mass_balance
from gemini.modules.heating import CHP, Boiler
from gemini.modules.pumps import ESP, InjectionPump
from gemini.types import (
    HeatLoss,
    HeatSupplied,
    Inlet,
    Outlet,
    Output,
    Stream,
)
from gemini.types.ports import Ports
from gemini.types.results import ModuleResult, Values
from tests.fixtures.equivalence import STREAM_FIELDS, assert_close


class Radiator(Module):
    """Deliver a fixed share of the stream's heat to a consumer and lose a little."""

    def __init__(self):
        """Declare the ports and the energy outputs."""
        super().__init__()

        # Inlets
        self.supply_in = Inlet(Stream)

        # Outputs
        self.heat_supplied = Output(HeatSupplied)
        self.heat_loss = Output(HeatLoss)

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
        stage_count=10,
        head_coefficients=[10, 0, 0, 0, 0, 0],
        power_coefficients=[1, 0, 0, 0, 0, 0],
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


GAS_FACTOR = 56.6 / 1e9
"""Natural-gas CO2 factor [kg/J] of the upstream GEMINI doublet example: 56.6 kg/GJ."""

GRID_FACTOR = 0.3 / 3.6e6
"""Grid-electricity CO2 factor [kg/J] of the upstream GEMINI doublet example: 0.3 kg/kWh."""


class GasHeatedInjection(Module):
    """Heat a return stream with a CHP and a boiler, then pump it into an injector."""

    def __init__(self):
        """Declare the three leaves and the plant ports."""
        super().__init__()

        # Modules
        self.chp = CHP().update_params(
            electric_capacity=1e5,
            electric_efficiency=0.4,
            thermal_efficiency=0.45,
            maximum_outlet_temperature=363.15,
        )
        self.boiler = Boiler().update_params(fuel_type="gas", capacity=1e6, efficiency=0.9)
        self.pump = InjectionPump().update_params(efficiency=0.8)

        # Inlets
        self.return_in = Inlet(Stream)

        # Outlets
        self.injected = Outlet(Stream)

    def forward(self, inlets):
        """Pass the stream through CHP, boiler and pump in flow order."""

        # Modules
        heated = self.chp(inlet=inlets.return_in).outlets.outlet
        topped = self.boiler(inlet=heated).outlets.outlet
        pumped = self.pump(suction=topped)

        # Outlets
        injected = pumped.outlets.discharge

        outlets = dict(injected=injected)
        return outlets


@pytest.mark.parametrize("load", [0.2, 1.0])
def test_emissions_charge_fuel_and_net_grid_electricity(load):
    """Fuel is charged in full; CHP electricity offsets the 60 kW pump before the grid."""
    plant = GasHeatedInjection()
    plant.set_inputs(
        {
            "chp.load_fraction": load,
            "boiler.temperature_setpoint": 343.15,
            "pump.pressure_setpoint": 50e5,
        }
    )
    result = plant(return_in=Stream(m_dot=10, T=313.15, p=2e5))
    flows = collect_flows(result)
    pump_power = 10 / 1000 * 48e5 / 0.8
    assert flows["electricity"] == pytest.approx(pump_power)
    assert flows["electricity_generated"] == pytest.approx(load * 1e5)
    grid = {0.2: pump_power - 2e4, 1.0: 0.0}[load]
    expected = flows["fuel"] * GAS_FACTOR + grid * GRID_FACTOR
    assert emissions(result, GAS_FACTOR, GRID_FACTOR) == pytest.approx(expected, rel=1e-12)


def test_emissions_without_energy_outputs_are_zero():
    """A leaf that burns and draws nothing emits nothing."""
    result = Boiler().update_params(fuel_type="gas", capacity=1e6, efficiency=0.9)(
        inlet=Stream(m_dot=10, T=350, p=2e5), temperature_setpoint=340
    )
    assert emissions(result, GAS_FACTOR, GRID_FACTOR) == 0


def _stack_streams(streams):
    return Stream(
        **{field: np.array([getattr(s, field) for s in streams]) for field in STREAM_FIELDS},
        fluid=streams[0].fluid,
    )


def _stack_results(results):
    """Return one result whose outputs and streams are arrays over the rows of ``results``."""
    first = results[0]
    return ModuleResult(
        outputs=Values(
            {name: np.array([r.outputs[name] for r in results]) for name in first.outputs}
        ),
        inlets=Ports({n: _stack_streams([r.inlets[n] for r in results]) for n in first.inlets}),
        outlets=Ports({n: _stack_streams([r.outlets[n] for r in results]) for n in first.outlets}),
        inputs={name: np.array([r.inputs[name] for r in results]) for name in first.inputs},
    )


def _assert_balances_match(module, results, expected_keys):
    stacked = _stack_results(results)
    for audit in (mass_balance, energy_balance):
        per_row = [audit(module, result) for result in results]
        together = audit(module, stacked)
        for key in expected_keys[audit]:
            assert_close(together[key], [row[key] for row in per_row], f"{audit.__name__}.{key}")
    flows = [collect_flows(result) for result in results]
    for key, values in collect_flows(stacked).items():
        assert_close(values, [row[key] for row in flows], key)
    per_row = [emissions(result, 0.2, 0.4) for result in results]
    assert_close(emissions(stacked, 0.2, 0.4), per_row, "emissions")


BALANCE_KEYS = {
    mass_balance: ("in", "out", "residual", "relative_residual"),
    energy_balance: ("in", "out", "residual", "relative_residual", "thermal_residual", "losses"),
}


@pytest.mark.parametrize("fuel", ["electric", "gas"])
def test_balances_match_on_stacked_boiler_results(fuel):
    """Audits and emissions on array-valued results equal the audits per row."""
    boiler = Boiler().update_params(fuel_type=fuel, capacity=1e6, efficiency=0.9)
    results = [
        boiler(inlet=Stream(m_dot=m_dot, T=300, p=1e6), temperature_setpoint=setpoint)
        for m_dot, setpoint in [(10, 320), (2, 310), (0.5, 300)]
    ]
    _assert_balances_match(boiler, results, BALANCE_KEYS)


def test_balances_match_on_stacked_radiator_results():
    """Supplied heat and loss outputs, with a residual of either sign, audit per row."""
    radiator = Radiator()
    results = [radiator(supply_in=Stream(m_dot=m_dot, T=350, p=3e5)) for m_dot in (0.0, 1.5, 12.0)]
    _assert_balances_match(radiator, results, BALANCE_KEYS)
