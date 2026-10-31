"""Levelised cost of thermal supply against the levelised cost of heat."""

import pytest

import gemini as gm
from gemini.modules import CoolingGrid
from gemini.units import SECONDS_PER_YEAR
from tests.fixtures.costed_plants import day, heating_plant
from tests.fixtures.errors import raises
from tests.fixtures.result_tables import make_problem

PRICES = make_problem(assumptions=gm.Assumptions(prices={"electricity": 2e-8}))
HEAT = 1000.0 * SECONDS_PER_YEAR
OPEX = 10.0 + 1e-9 * HEAT + 2e-8 * 100.0 * SECONDS_PER_YEAR
"""Yearly cost of the heating plant under ``PRICES``: fixed, variable and electricity."""


def both_products():
    """Return a heat plant that also has a cooling consumer."""
    plant = heating_plant()
    plant._add_module("cool", CoolingGrid())
    return plant


def test_lcts_is_the_cost_of_heat_and_cold_together():
    """``lcoh`` with the whole cost on the heat, spread over both products; no share needed."""
    plant, run = both_products(), day(cold=500.0)
    shared = make_problem(
        assumptions=gm.Assumptions(heat_cost_share=1.0, prices={"electricity": 2e-8})
    )
    lcoh = gm.evaluate.lcoh(plant, shared, run, 0.05, 20)
    result = gm.evaluate.lcts(plant, PRICES, run, 0.05, 20)
    heat, cold = result["heat"]["value"], result["cold"]["value"]
    assert heat == pytest.approx(HEAT) and cold == pytest.approx(HEAT / 2)
    assert result["value"] == pytest.approx(
        lcoh["value"] * lcoh["energy"]["value"] / (heat + cold), rel=1e-12
    )
    assert (
        result["unit"] == "EUR/J" and result["heat"]["unit"] == result["cold"]["unit"] == "J/year"
    )
    assert result["annualised_cost"]["unit"] == "EUR/year"


def test_lcts_of_one_product_is_its_levelised_cost():
    """A plant that delivers only heat has the same cost per joule both ways."""
    expected = gm.evaluate.lcoh(heating_plant(), PRICES, day(), 0.05, 20)["value"]
    result = gm.evaluate.lcts(heating_plant(), PRICES, day(), 0.05, 20)
    assert result["value"] == pytest.approx(expected, rel=1e-12)
    assert result["cold"]["value"] == 0


def test_lcts_without_energy_has_no_value():
    """No heat and no cold: a reason, as ``lcoh`` gives; raised by default."""
    idle = day(heat=0.0)
    recorded = gm.evaluate.lcts(heating_plant(), PRICES, idle, 0.05, 20, on_error="record")
    assert recorded["value"] is None and "neither heat nor cold" in recorded["reason"]
    assert recorded["unit"] == "EUR/J"
    with raises(gm.errors.ValidationError, "no_value", match="neither heat nor cold"):
        gm.evaluate.lcts(heating_plant(), PRICES, idle, 0.05, 20)
