"""Splitter mass division, unchanged stream states and limits."""

import pytest

import gemini as gm
from gemini.core.modules import energy_balance, mass_balance
from gemini.core.modules.piping import Splitter
from gemini.core.types import WATER, Stream

FEED = Stream(m_dot=10, T=353.15, p=5e5, fluid=WATER)


def test_split_divides_mass_and_keeps_the_state():
    """The second branch takes the split fraction; both keep T, p and fluid."""
    result = Splitter()(feed_in=FEED, split_fraction=0.25)
    first, second = result.outlets.first_out, result.outlets.second_out
    assert (first.m_dot, second.m_dot) == (7.5, 2.5)
    for branch in (first, second):
        assert (branch.T, branch.p, branch.fluid) == (FEED.T, FEED.p, WATER)
    assert mass_balance(Splitter(), result)["residual"] == 0
    assert energy_balance(Splitter(), result)["relative_residual"] < 1e-12


def test_limits_of_the_split():
    """Fractions 0 and 1 send everything to one branch; zero feed gives two stopped branches."""
    assert Splitter()(feed_in=FEED, split_fraction=0).outlets.second_out.m_dot == 0
    assert Splitter()(feed_in=FEED, split_fraction=1).outlets.first_out.m_dot == 0
    stopped = Splitter()(feed_in=FEED.with_(m_dot=0), split_fraction=0.5).outlets
    assert stopped.first_out.m_dot == stopped.second_out.m_dot == 0
    odd = Splitter()(feed_in=FEED.with_(m_dot=0.7), split_fraction=0.3)
    assert mass_balance(Splitter(), odd)["relative_residual"] < 1e-15


def test_invalid_inputs_raise():
    """Reverse feed, a fraction outside [0, 1] and a missing command are rejected."""
    with pytest.raises(gm.errors.PhysicsRangeError, match="splitter: feed_in.m_dot = -1"):
        Splitter()(feed_in=FEED.with_(m_dot=-1), split_fraction=0.5)
    with pytest.raises(gm.errors.DeclarationError):
        Splitter()(feed_in=FEED, split_fraction=1.2)
    with pytest.raises(gm.errors.MissingValueError):
        Splitter()(feed_in=FEED)
