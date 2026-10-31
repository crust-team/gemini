"""The marginal cost of a source, from the prices of a problem."""

import numpy as np
import pytest

import gemini as gm
from gemini.run._utils import sources
from tests.fixtures.errors import raises


def costs(steps=2, **fields):
    """Return the prices of ``Assumptions`` with ``fields`` for ``steps`` rows."""
    return sources.Costs(gm.Assumptions(**fields), steps)


def test_a_cost_is_the_price_over_the_efficiency():
    """One number per step, whatever the efficiency."""
    cost = costs(prices={"electricity": 3e-8}).electric("hp", 3.0)
    assert cost == pytest.approx([1e-8, 1e-8])


def test_a_price_profile_gives_a_cost_per_step():
    """A profile on the demand index reaches each step."""
    cost = costs(prices={"electricity": [1e-8, 3e-8]}).electric("hp", 1.0)
    assert cost.tolist() == pytest.approx([1e-8, 3e-8])


def test_the_carbon_price_adds_the_emission_of_the_carrier():
    """Gas burns to CO2; electricity emits what its factor says."""
    gas = costs(prices={"gas": 0.0}, co2_price=1.0).gas("boiler", 1.0)
    assert gas[0] == pytest.approx(sources.dispatch.methane_emission_factor())
    power = costs(prices={"electricity": 0.0}, co2_price=1.0, electricity_emission_factor=2e-8)
    assert power.electric("hp", 1.0)[0] == pytest.approx(2e-8)


def test_a_missing_price_names_the_carrier_and_the_source():
    """The price is a part of the problem: ``missing_value``."""
    with raises(gm.errors.ValidationError, "missing_value", match="boiler"):
        costs().gas("boiler", 0.9)


def test_drive_heat_costs_the_cheapest_heat_over_the_cop():
    """Each step takes its cheapest source."""
    cheapest = [np.array([1.0, 4.0]), np.array([2.0, 2.0])]
    assert sources.drive_cost(cheapest, 2.0).tolist() == [0.5, 1.0]
