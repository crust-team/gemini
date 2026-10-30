"""CO2 of a run against the balance code and a hand sum."""

from types import SimpleNamespace

import pytest

import gemini as gm
from gemini.economics import emissions as module
from gemini.modules.balance import emissions
from tests.fixtures.costed_plants import HOURS, day
from tests.fixtures.result_tables import make_results

DAY = HOURS * 3600.0
"""Seconds of the runs below."""


def test_co2_is_fuel_and_grid_electricity_times_their_factors():
    """1000 W of fuel and 60 W of grid electricity (100 consumed, 40 generated) for a day."""
    values = gm.economics.Assumptions(electricity_emission_factor=1e-7)
    result = gm.economics.co2(day(electricity=100.0, generated=40.0, fuel=1000.0), values)
    assert result["unit"] == "kg"
    assert result["fuel_energy"] == 1000.0 * DAY
    assert result["grid_energy"] == 60.0 * DAY
    assert result["value"] == pytest.approx(1000.0 * DAY * 56.1e-9 + 60.0 * DAY * 1e-7, rel=1e-12)
    assert result["window"] == DAY


def test_co2_is_the_balance_emissions_rate_times_the_tick():
    """One tick gives exactly ``emissions`` of the same leaf totals times its duration."""
    one = make_results(
        {"a": {"electricity": [30.0], "electricity_generated": [10.0]}, "b": {"fuel": [500.0]}}
    )
    values = gm.economics.Assumptions(electricity_emission_factor=2e-7)
    leaf = SimpleNamespace(
        children={}, outputs={"electricity": 30.0, "electricity_generated": 10.0, "fuel": 500.0}
    )
    rate = emissions({"": leaf}, values.fuel_emission_factor, 2e-7)
    assert gm.economics.co2(one, values)["value"] == pytest.approx(rate * 3600.0, rel=1e-12)


def test_a_surplus_of_generation_earns_no_credit():
    """Generation above consumption draws no grid electricity, and the factor is not needed."""
    result = gm.economics.co2(day(electricity=10.0, generated=50.0, fuel=0.0))
    assert result["grid_energy"] == 0.0
    assert result["value"] == 0.0


def test_grid_electricity_without_a_factor_is_refused():
    """Drawing electricity with no ``electricity_emission_factor`` names what to give."""
    with pytest.raises(gm.errors.ValidationError, match="electricity_emission_factor") as error:
        gm.economics.co2(day())
    assert error.value.code == "missing_value"


def test_source_energies_of_a_run_without_fuel_or_electricity_is_zero():
    """A run without those columns draws nothing."""
    quiet = make_results({"heat": {"heat_supplied": [1.0, 2.0]}})
    assert module.source_energies(quiet) == (0.0, 0.0)
