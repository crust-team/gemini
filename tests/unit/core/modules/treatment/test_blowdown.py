"""Blowdown bleed split, conservation and limits."""

import pytest

import gemini as gm
from gemini.core.modules.balance import energy_balance, mass_balance
from gemini.core.modules.treatment import Blowdown
from gemini.core.types.flows import Stream
from tests.fixtures.equivalence import assert_module_matches

FEED = Stream(m_dot=8, T=330, p=3e5)


def test_bleed_split_conserves_mass_and_energy():
    """The commanded share drains at the feed state; the rest is retained."""
    blowdown = Blowdown()
    result = blowdown(feed_in=FEED, blowdown_fraction=0.25)
    retained, drained = result.outlets.retained_out, result.outlets.blowdown_out
    assert drained == FEED.with_(m_dot=2) and retained == FEED.with_(m_dot=6)
    assert result.outputs.blowdown_mass_flow == 2
    assert "modelled" not in result.outputs and "heat_loss" not in result.outputs
    assert mass_balance(blowdown, result)["residual"] == 0
    assert energy_balance(blowdown, result)["relative_residual"] < 1e-12


def test_limits():
    """Closed and fully open bleeds, zero flow, reverse flow and a missing command."""
    blowdown = Blowdown()
    assert blowdown(feed_in=FEED, blowdown_fraction=0).outlets.blowdown_out.m_dot == 0
    assert blowdown(feed_in=FEED, blowdown_fraction=1).outlets.retained_out.m_dot == 0
    stopped = blowdown(feed_in=FEED.with_(m_dot=0), blowdown_fraction=0.1)
    assert stopped.outputs.blowdown_mass_flow == 0
    with pytest.raises(gm.errors.PhysicsRangeError, match="feed_in.m_dot"):
        blowdown(feed_in=FEED.with_(m_dot=-1), blowdown_fraction=0.1)
    with pytest.raises(gm.errors.MissingValueError):
        blowdown(feed_in=FEED)


def test_blowdown_matches_traced():
    """The split traces and equals one call per row."""
    rows = [
        dict(feed_in=Stream(m_dot=m_dot, T=310, p=2e5), blowdown_fraction=fraction)
        for m_dot, fraction in [(0, 0.1), (10, 0), (30, 0.05), (30, 1)]
    ]
    assert_module_matches(Blowdown(), rows)
