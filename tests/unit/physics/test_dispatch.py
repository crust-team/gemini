"""The daily energy balance of a schedule."""

import numpy as np
import pytest

from gemini.physics import dispatch
from tests.fixtures.equivalence import assert_function_matches


def test_a_doublet_gives_the_heat_at_the_allowed_cooling():
    """The flow that gives the need; nothing is left."""
    flow, remaining = dispatch.doublet_flow(1e6, 1e8, 0.01, 0.1)
    assert flow == pytest.approx(0.01) and remaining == pytest.approx(0)


def test_the_flow_is_clipped_to_its_limits():
    """Below the minimum it runs at the minimum; above the maximum the rest stays."""
    assert dispatch.doublet_flow(1e5, 1e8, 0.01, 0.1) == (0.01, 0)
    flow, remaining = dispatch.doublet_flow(2e7, 1e8, 0.01, 0.1)
    assert flow == 0.1 and remaining == pytest.approx(1e7)


def test_without_a_need_the_doublet_is_off():
    """Zero flow, not the minimum."""
    assert dispatch.doublet_flow(0.0, 1e8, 0.01, 0.1) == (0, 0)


def test_the_circuit_flow_and_the_share():
    """A heat balance and a ratio."""
    assert dispatch.circuit_flow(4e6, 4000.0, 40.0) == pytest.approx(25)
    assert dispatch.flow_share(1.0, 3.0) == 0.25
    assert dispatch.flow_share(0.0, 0.0) == 1


def test_on_arrays():
    """Every branch agrees on arrays."""
    rows = [(0.0, 1e8, 0.01, 0.1), (1e5, 1e8, 0.01, 0.1), (2e7, 1e8, 0.01, 0.1)]
    assert_function_matches(dispatch.doublet_flow, rows)
    assert_function_matches(dispatch.circuit_flow, [(4e6, 4000.0, 40.0), (0.0, 4000.0, 40.0)])
    assert_function_matches(dispatch.flow_share, [(1.0, 3.0), (0.0, 0.0)])


def test_the_cheapest_source_loads_first():
    """Each up to its capacity in the order of the costs; what no source takes is left."""
    assert dispatch.loaded_by_cost(7.0, [5.0, 1.0, 9.0], [3.0, 2.0, 1.0]) == [0, 0, 7]
    assert dispatch.loaded_by_cost(7.0, [5.0, 1.0, 9.0], [1.0, 2.0, 3.0]) == [5, 1, 1]
    assert dispatch.loaded_by_cost(9.0, [5.0, 1.0], [1.0, 2.0]) == [5, 1]
    assert dispatch.loaded_by_cost(3.0, [5.0, 1.0], [2.0, 1.0]) == [2, 1]


def test_sources_of_equal_cost_load_in_plant_order():
    """A tie keeps the order of the list."""
    assert dispatch.loaded_by_cost(6.0, [4.0, 4.0, 4.0], [1.0, 1.0, 1.0]) == [4, 2, 0]


def test_the_order_can_change_from_step_to_step():
    """Costs along the steps give an order per step."""
    taken = dispatch.loaded_by_cost(
        np.array([3.0, 3.0]),
        [np.array([2.0, 2.0]), np.array([5.0, 5.0])],
        [np.array([1.0, 2.0]), np.array([2.0, 1.0])],
    )
    assert taken[0].tolist() == [2, 0] and taken[1].tolist() == [1, 3]


def test_the_marginal_cost_is_price_over_efficiency_plus_carbon():
    """Energy price and CO2 cost, per joule delivered."""
    assert dispatch.marginal_cost(3.0, 2.0, 10.0, 0.1) == pytest.approx(2.0)


def test_methane_emits_its_stoichiometric_carbon_dioxide():
    """2.74 kg of CO2 per kg of methane at 50 MJ/kg."""
    assert dispatch.methane_emission_factor() == pytest.approx(2.743 / 50e6, rel=1e-3)


def test_a_heat_pump_cop_follows_the_lift():
    """Heating at a 50 K lift with half the Carnot COP; cooling at 15 K."""
    assert dispatch.heat_pump_cop(True, 0.5, 5.0, 373.15, 323.15) == pytest.approx(
        0.5 * 373.15 / 50
    )
    assert dispatch.heat_pump_cop(False, 0.5, 5.0, 308.15, 293.15) == pytest.approx(
        0.5 * 293.15 / 15
    )


def test_the_temperature_moves_with_the_duty():
    """At a constant flow, a quarter of the duty is a quarter of the way."""
    assert dispatch.temperature_after(298.0, 290.0, 0.25) == 296


def test_the_two_paths_agree():
    """Floats and arrays give the same numbers."""
    assert_function_matches(dispatch.temperature_after, [(298.0, 290.0, 0.25), (280.0, 280.0, 1.0)])
