"""First-law and zero-flow boiler limits."""

import pytest

import gemini as gm
from gemini.modules import GasGrid
from gemini.modules.heating import Boiler, ElectricBoiler
from gemini.physics import gas
from gemini.types.flows import Stream
from tests.fixtures.equivalence import assert_module_matches

GRID_GAS = GasGrid()().outlets.fluid_out
COPRODUCED = gm.Fluid(kind="gas", gas_composition={"CH4": 0.8, "CO2": 0.2})
WATER = Stream(m_dot=10, T=300, p=1e6)


def test_capacity_balance_and_no_cooling():
    """Capacity caps heat, energy input accounts for efficiency, and the boiler never cools."""
    c = Boiler().update_params(capacity=100000, efficiency=0.8)
    s = Stream(m_dot=10, T=300, p=1e6)
    result = c(temperature_setpoint=360, fluid_in=s, fuel_in=GRID_GAS)
    out, streams = result.outputs, result.outlets
    assert out.is_capped and out.duty == 100000 and out.fuel_or_power == 125000
    assert (streams["fluid_out"].T - s.T) * s.m_dot * 4217.4 == pytest.approx(out.duty)
    assert streams["fluid_out"].m_dot == s.m_dot and streams["fluid_out"].p == s.p
    out = c(temperature_setpoint=290, fluid_in=s, fuel_in=GRID_GAS).outputs
    assert out.duty == 0 and out.fluid_out_T == 300
    out = c(temperature_setpoint=360, fluid_in=s.with_(m_dot=0), fuel_in=GRID_GAS).outputs
    assert out.duty == 0 and out.fluid_out_T == 300


def test_traced_call_matches_one_call_per_row():
    """Capped, uncapped, no-heating-needed and stopped rows trace and equal one call per row."""
    cases = [(10, 360), (1, 310), (10, 290), (0, 360), (2, 305)]
    gas = Boiler().update_params(capacity=100000, efficiency=0.8)
    rows = [
        dict(
            fluid_in=Stream(m_dot=m, T=300, p=1e6), fuel_in=GRID_GAS, temperature_setpoint=setpoint
        )
        for m, setpoint in cases
    ]
    assert_module_matches(gas, rows)
    electric = ElectricBoiler().update_params(capacity=100000, efficiency=0.8)
    rows = [
        dict(fluid_in=Stream(m_dot=m, T=300, p=1e6), temperature_setpoint=setpoint)
        for m, setpoint in cases
    ]
    assert_module_matches(electric, rows)


def gas_stream(flow, marked=True):
    """Return co-produced gas of ``flow`` [kg/s], on a stream with or without a grid connection."""
    fluid = COPRODUCED.with_grid(gas.GRID_COMPOSITION) if marked else COPRODUCED
    return Stream(m_dot=flow, T=330, p=2e5, fluid=fluid)


def test_co_produced_gas_is_burned_first_and_the_grid_covers_the_rest():
    """A boiler needs duty over efficiency; it burns what comes and buys the difference."""
    boiler = Boiler().update_params(capacity=1e6, efficiency=0.8)
    heating_value = COPRODUCED.heating_value()
    available = 0.01 * heating_value
    result = boiler(fluid_in=WATER, fuel_in=gas_stream(0.01), temperature_setpoint=320)
    out = result.outputs
    assert out.fuel == pytest.approx(out.duty / 0.8)
    assert out.fuel_coproduced == pytest.approx(available)
    assert out.fuel_purchased == pytest.approx(out.fuel - available)
    assert out.burned_mass_flow == pytest.approx(0.01)
    assert result.outlets.gas_out.m_dot == pytest.approx(0, abs=1e-15)
    expected = available * COPRODUCED.emission_factor()
    expected += out.fuel_purchased * gas.emission_per_energy(gas.GRID_COMPOSITION)
    assert out.co2_emission == pytest.approx(expected)


def test_enough_co_produced_gas_buys_nothing_and_passes_the_surplus():
    """With gas to spare nothing is bought and ``gas_out`` carries the rest."""
    boiler = Boiler().update_params(capacity=1e6, efficiency=0.8)
    result = boiler(fluid_in=WATER, fuel_in=gas_stream(1.0), temperature_setpoint=320)
    out = result.outputs
    assert out.fuel_purchased == 0 and out.fuel_coproduced == pytest.approx(out.fuel)
    assert result.outlets.gas_out.m_dot == pytest.approx(1.0 - out.burned_mass_flow)


def test_no_co_produced_gas_buys_everything():
    """On a grid alone all fuel is bought and all its CO2 comes from the grid composition."""
    boiler = Boiler().update_params(capacity=1e6, efficiency=0.8)
    out = boiler(fluid_in=WATER, fuel_in=GRID_GAS, temperature_setpoint=320).outputs
    assert out.fuel_coproduced == 0 and out.fuel_purchased == pytest.approx(out.fuel)
    assert out.co2_emission == pytest.approx(
        out.fuel * gas.emission_per_energy(gas.GRID_COMPOSITION)
    )


def test_without_a_grid_mark_the_gas_limits_the_duty():
    """A burner on an unmarked stream may not buy: the energy of the stream caps it."""
    boiler = Boiler().update_params(capacity=1e6, efficiency=0.8)
    result = boiler(fluid_in=WATER, fuel_in=gas_stream(0.002, False), temperature_setpoint=360)
    out = result.outputs
    assert out.fuel_purchased == pytest.approx(0, abs=1e-6) and out.is_capped
    assert out.duty == pytest.approx(0.002 * COPRODUCED.heating_value() * 0.8)


def test_an_electric_boiler_has_no_gas_ports():
    """Only the water side."""
    assert list(ElectricBoiler().inlets()) == ["fluid_in", "power_in"]
    assert list(ElectricBoiler().outlets()) == ["fluid_out"]
