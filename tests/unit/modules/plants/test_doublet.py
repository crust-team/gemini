"""The reusable doublet produces through its upper limb and injects through its lower limb."""

import pytest

from gemini.types import Stream


@pytest.fixture
def doublet(fresh_plant):
    """Return the example doublet with its production controls set."""
    module = fresh_plant.doublet
    module.set_inputs({"reservoir.production_rate": 40.0, "esp.frequency": 50.0})
    return module


def test_supply_is_the_riser_wellhead_and_return_reaches_the_sink(doublet):
    """Both limbs run once; electricity and heat loss sum over every leaf call."""
    returned = Stream(m_dot=40, T=330, p=5e6, fluid=doublet.fluid)
    result = doublet(return_in=returned)
    leaves = result.leaves()
    assert result.outlets.supply_out == leaves["riser"].outlets.wellhead
    assert leaves["injector"].inlets.wellhead == returned
    assert leaves["sink"].inlets.sandface == leaves["injector"].outlets.bottom
    electricity = sum(leaf.outputs.get("electricity", 0.0) for leaf in leaves.values())
    assert result.outputs.electricity == pytest.approx(electricity)
    heat_loss = sum(leaf.outputs.get("heat_loss", 0.0) for leaf in leaves.values())
    assert result.outputs.heat_loss == pytest.approx(heat_loss)
