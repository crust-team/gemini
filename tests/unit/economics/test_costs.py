"""Investment and operating cost against the declared costs and hand sums."""

import pytest

import gemini as gm
from gemini.economics import costs
from gemini.physics.units import SECONDS_PER_YEAR
from tests.fixtures.costed_plants import cooling_plant, day, heating_plant

HEAT_PER_YEAR = 1000.0 * SECONDS_PER_YEAR
"""Heat [J/year] of 1000 W delivered all year."""

GRID_PER_YEAR = 100.0 * SECONDS_PER_YEAR
"""Grid electricity [J/year] of 100 W drawn all year."""


def test_capex_is_the_declared_cost_with_its_source():
    """The investment is ``total_cost``'s, in its currency, with year and source."""
    result = gm.economics.capex(heating_plant())
    assert result == {
        "value": 1000.0,
        "unit": "EUR",
        "reason": None,
        "price_year": 2024,
        "source": "test fixture",
    }


def test_capex_of_a_plant_without_declared_costs_is_null_with_a_reason():
    """Built-in modules declare no cost: nothing is invented."""
    result = gm.economics.capex(heating_plant(costed=False))
    assert result["value"] is None
    assert result["reason"] == costs.NO_COST
    assert result["unit"] == "EUR"
    no_euro = gm.economics.capex(
        heating_plant(costed=False), gm.economics.Assumptions(currency="USD")
    )
    assert no_euro["unit"] == "USD"


def test_the_example_plant_has_no_declared_cost(shared_plant):
    """The doublet heat plant is built of built-in modules, so it has no capex."""
    assert gm.economics.capex(shared_plant)["value"] is None


def test_annual_energies_scale_the_window_to_a_year():
    """A day of 1000 W of heat is 1000 W for a year; 100 W of electricity is all grid."""
    annual = costs.annual_energies(heating_plant(), day())
    assert annual.heat == pytest.approx(HEAT_PER_YEAR, rel=1e-12)
    assert annual.grid == pytest.approx(GRID_PER_YEAR, rel=1e-12)
    assert annual.cold == 0.0 and annual.fuel == 0.0


def test_opex_adds_fixed_variable_and_energy_bill():
    """10 EUR fixed, 1e-9 EUR/J of heat and the electricity at 2e-8 EUR/J."""
    values = gm.economics.Assumptions(electricity_price=2e-8)
    result = gm.economics.opex(heating_plant(), day(), values)
    components = result["components"]
    assert components["fixed"] == 10.0
    assert components["variable"] == pytest.approx(1e-9 * HEAT_PER_YEAR, rel=1e-12)
    assert components["electricity"] == pytest.approx(2e-8 * GRID_PER_YEAR, rel=1e-12)
    assert components["fuel"] == 0.0
    assert result["value"] == pytest.approx(sum(components.values()), rel=1e-12)
    assert result["unit"] == "EUR/year"


def test_opex_needs_the_price_of_an_energy_the_run_draws():
    """Electricity is drawn but has no price: the user is asked, not guessed for."""
    with pytest.raises(gm.errors.ValidationError, match="electricity_price") as error:
        gm.economics.opex(heating_plant(), day())
    assert error.value.code == "missing_value"


def test_opex_without_declared_costs_reports_only_the_bill():
    """No declared cost: the value is null and says why; the bill is still given."""
    values = gm.economics.Assumptions(electricity_price=2e-8)
    result = gm.economics.opex(heating_plant(costed=False), day(), values)
    assert result["value"] is None and result["reason"] == costs.NO_COST
    assert result["components"]["electricity"] == pytest.approx(2e-8 * GRID_PER_YEAR, rel=1e-12)


def test_opex_refuses_prices_in_another_currency():
    """A cost in EUR and assumptions in USD do not mix."""
    values = gm.economics.Assumptions(electricity_price=2e-8, currency="USD")
    with pytest.raises(gm.errors.ValidationError, match="currency"):
        gm.economics.opex(heating_plant(), day(), values)


def test_cold_is_counted_from_the_cooling_consumers():
    """Cold delivered per year comes from ``heat_absorbed`` of the cooling consumers."""
    annual = costs.annual_energies(cooling_plant(), day(heat=None, cold=300.0))
    assert annual.cold == pytest.approx(300.0 * SECONDS_PER_YEAR, rel=1e-12)
    assert annual.heat == 0.0
