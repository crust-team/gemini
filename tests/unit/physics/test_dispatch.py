"""The daily energy balance of a schedule."""

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
