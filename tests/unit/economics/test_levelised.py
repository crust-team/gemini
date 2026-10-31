"""Levelised cost of heat and cold against the closed-form annuity."""

import pytest

import gemini as gm
from gemini.economics import levelised
from gemini.modules import CoolingConsumer
from gemini.physics.units import SECONDS_PER_YEAR
from tests.fixtures.costed_plants import cooling_plant, day, heating_plant
from tests.fixtures.errors import raises

PRICES = gm.economics.Assumptions(electricity_price=2e-8)
HEAT = 1000.0 * SECONDS_PER_YEAR
OPEX = 10.0 + 1e-9 * HEAT + 2e-8 * 100.0 * SECONDS_PER_YEAR
"""Yearly cost of the heating plant under ``PRICES``: fixed, variable and electricity."""


def test_annuity_is_the_discounted_year_count():
    """Ten years at 5 % are 7.7217 discounted years; at 0 % they are ten."""
    assert levelised.annuity(0.05, 10) == pytest.approx(7.721734929, rel=1e-9)
    assert levelised.annuity(0.0, 10) == 10.0


def test_lcoh_is_discounted_cost_over_discounted_heat():
    """(capex + opex A) / (heat A) with the annuity factor of 5 % over 20 years."""
    factor = (1 - 1.05**-20) / 0.05
    result = gm.economics.lcoh(heating_plant(), day(), 0.05, 20, PRICES)
    assert result["value"] == pytest.approx((1000.0 + OPEX * factor) / (HEAT * factor), rel=1e-12)
    assert result["unit"] == "EUR/J"
    assert result["capex"] == {"value": 1000.0, "unit": "EUR"}
    assert result["opex"]["value"] == pytest.approx(OPEX, rel=1e-12)


def test_lcoh_at_zero_rate_spreads_the_cost_over_the_years():
    """Without discounting, the cost over the lifetime divided by the heat over the lifetime."""
    result = gm.economics.lcoh(heating_plant(), day(), 0.0, 10, PRICES)
    assert result["value"] == pytest.approx((1000.0 + OPEX * 10) / (HEAT * 10), rel=1e-12)


def test_the_rate_and_lifetime_come_from_the_assumptions():
    """Given in the assumptions, they give the same value as passed explicitly."""
    both = gm.economics.Assumptions(electricity_price=2e-8, discount_rate=0.05, lifetime_years=20)
    explicit = gm.economics.lcoh(heating_plant(), day(), 0.05, 20, PRICES)
    assert gm.economics.lcoh(heating_plant(), day(), assumptions=both) == explicit


def test_a_missing_rate_is_asked_for():
    """No rate anywhere raises with the missing-value code."""
    with pytest.raises(gm.errors.ValidationError, match="discount_rate") as error:
        gm.economics.lcoh(heating_plant(), day(), None, 20, PRICES)
    assert error.value.code == "missing_assumption"


def test_null_with_a_reason_when_the_cost_or_the_heat_is_missing():
    """No declared cost, no heat delivered, or heat and cold together give no value."""
    unpriced = gm.economics.lcoh(
        heating_plant(costed=False), day(), 0.05, 20, PRICES, on_error="record"
    )
    assert unpriced["value"] is None and "no module declares a cost" in unpriced["reason"]
    idle = gm.economics.lcoh(heating_plant(), day(heat=0.0), 0.05, 20, PRICES, on_error="record")
    assert idle["reason"] == "the run delivers no heat"
    plant = heating_plant()
    plant.add_module("cool", CoolingConsumer())
    both = gm.economics.lcoh(plant, day(cold=100.0), 0.05, 20, PRICES, on_error="record")
    assert both["value"] is None and "split of its cost" in both["reason"]
    with raises(gm.errors.ValidationError, "no_value", match="split of its cost"):
        gm.economics.lcoh(plant, day(cold=100.0), 0.05, 20, PRICES)


def test_a_share_splits_the_cost_of_a_plant_with_two_products():
    """``heat_cost_share`` charges that part of the cost to heat and the rest to cold."""
    plant = heating_plant()
    plant.add_module("cool", CoolingConsumer())
    run = day(cold=100.0)
    values = PRICES.model_copy(update={"heat_cost_share": 0.8})
    heat = gm.economics.lcoh(plant, run, 0.05, 20, values)
    cold = gm.economics.lcoc(plant, run, 0.05, 20, values)
    assert heat["value"] * heat["energy"]["value"] / 0.8 == pytest.approx(
        cold["value"] * cold["energy"]["value"] / 0.2
    )


def test_lcoc_divides_by_the_cold_delivered():
    """The cooling plant (2000 EUR, no running cost, 300 W of cold) over 10 years at 0 %."""
    values = gm.economics.Assumptions(electricity_price=2e-8)
    result = gm.economics.lcoc(cooling_plant(), day(heat=None, cold=300.0), 0.0, 10, values)
    opex = 2e-8 * 100.0 * SECONDS_PER_YEAR
    expected = (2000.0 + opex * 10) / (300.0 * SECONDS_PER_YEAR * 10)
    assert result["value"] == pytest.approx(expected, rel=1e-12)
