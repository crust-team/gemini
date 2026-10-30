"""Boiler fuel input, engine Willans line and flare emissions."""

import pytest

from gemini.physics import combustion
from tests.fixtures.equivalence import assert_function_matches


def test_willans_line_and_engine_flows():
    """Full load needs capacity over efficiency; no load needs the idle share; off is zero."""
    assert combustion.willans_fuel_input(1.0, 400.0, 0.4, 0.1) == pytest.approx(1000)
    assert combustion.willans_fuel_input(0.5, 400.0, 0.4, 0.1) == pytest.approx(550)
    assert combustion.willans_fuel_input(0.0, 400.0, 0.4, 0.1) == 0
    assert combustion.engine_energy_flows(1000.0, 0.5, 400.0, 0.45) == (450.0, 200.0)
    rows = [(1.0, 400.0, 0.4, 0.1), (0.5, 400.0, 0.4, 0.1), (0.0, 400.0, 0.4, 0.1)]
    assert_function_matches(combustion.willans_fuel_input, rows)
    flows = [(1000.0, 0.5, 400.0, 0.45), (0.0, 0.0, 400.0, 0.45)]
    assert_function_matches(combustion.engine_energy_flows, flows)


def test_flare_emissions_follow_the_stoichiometry():
    """Burnt methane gives 44.01 / 16.043 kg CO2 per kg; a vent burns nothing."""
    co2, methane, fuel = combustion.flare_emissions(2.0, 0.1, 0.5, 0.98, 50e6)
    burnt = 0.98 * 0.5 * 2.0
    assert co2 == pytest.approx(0.2 + burnt * 0.04401 / 0.016043)
    assert methane == pytest.approx(1.0 - burnt)
    assert fuel == pytest.approx(burnt * 50e6)
    assert combustion.flare_emissions(2.0, 0.1, 0.5, 0.0, 50e6) == (0.2, 1.0, 0.0)
    rows = [(2.0, 0.1, 0.5, 0.98, 50e6), (2.0, 0.1, 0.5, 0.0, 50e6)]
    assert_function_matches(combustion.flare_emissions, rows)
