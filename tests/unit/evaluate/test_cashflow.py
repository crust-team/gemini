"""Net present value and payback against closed forms."""

import pytest

import gemini as gm
from gemini.units import SECONDS_PER_YEAR
from tests.fixtures.costed_plants import day, heating_plant
from tests.fixtures.errors import raises

HEAT = 1000.0 * SECONDS_PER_YEAR
OPEX = 10.0 + 1e-9 * HEAT + 2e-8 * 100.0 * SECONDS_PER_YEAR
SELLING = gm.Assumptions(prices={"electricity": 2e-8, "heat": 5e-8})
NET = 5e-8 * HEAT - OPEX
"""Yearly net cash flow of the heating plant when its heat sells at 5e-8 EUR/J."""


def test_npv_is_the_discounted_net_cash_flow_less_the_investment():
    """-capex + net * A with A the 5 % annuity over 20 years."""
    factor = (1 - 1.05**-20) / 0.05
    result = gm.evaluate.npv(heating_plant(), day(), 0.05, 20, SELLING)
    assert result["value"] == pytest.approx(NET * factor - 1000.0, rel=1e-12)
    assert result["unit"] == "EUR"
    assert result["net_cash_flow"]["value"] == pytest.approx(NET, rel=1e-12)
    assert result["net_cash_flow"]["unit"] == "EUR/year"


def test_payback_is_the_investment_over_the_net_cash_flow():
    """Simple payback in years, undiscounted."""
    result = gm.evaluate.payback(heating_plant(), day(), SELLING)
    assert result["value"] == pytest.approx(1000.0 / NET, rel=1e-12)
    assert result["unit"] == "year"


def test_payback_never_comes_when_revenue_does_not_cover_the_cost():
    """A heat price below the running cost gives null with the reason."""
    cheap = gm.Assumptions(prices={"electricity": 2e-8, "heat": 1e-9})
    result = gm.evaluate.payback(heating_plant(), day(), cheap, on_error="record")
    assert result["value"] is None
    assert result["reason"] == "the yearly revenue does not exceed the yearly cost"


def test_the_price_of_heat_is_asked_for_when_heat_is_delivered():
    """Heat is delivered but unpriced: the user is asked."""
    with pytest.raises(gm.errors.ValidationError, match="heat"):
        gm.evaluate.payback(heating_plant(), day(), gm.Assumptions(prices={"electricity": 2e-8}))


def test_a_plant_without_declared_cost_has_no_npv_or_payback():
    """Both are null with the reason of the missing cost."""
    plant = heating_plant(costed=False)
    values = gm.Assumptions(prices={"electricity": 2e-8, "heat": 5e-8})
    assert gm.evaluate.npv(plant, day(), 0.05, 20, values, on_error="record")["value"] is None
    recorded = gm.evaluate.payback(plant, day(), values, on_error="record")
    assert "no module declares a cost" in recorded["reason"]
    with raises(gm.errors.ValidationError, "no_value", match="no module declares a cost"):
        gm.evaluate.npv(plant, day(), 0.05, 20, values)
    with raises(gm.errors.ValidationError, "no_value", match="no module declares a cost"):
        gm.evaluate.payback(plant, day(), values)
