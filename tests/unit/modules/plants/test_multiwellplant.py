"""Multi-well field: production limbs mixed into one supply, return split over injectors."""

import pytest

import gemini as gm
from gemini.modules import energy_balance, mass_balance
from gemini.modules.plants import generators
from gemini.types import Stream

LIMB = ("reservoir", "well", "esp", "riser")


def _field(doublet, producers=2, injectors=1, rates=(40.0, 30.0)):
    """Return a field whose limbs copy the example doublet's equipment."""
    field = gm.plants.from_template(
        "MultiWellPlant", {"producers": producers, "injectors": injectors}
    )
    for limb, rate in zip(field.producers, rates):
        for name in LIMB:
            getattr(limb, name).load_state_dict(getattr(doublet, name).state_dict())
        limb.reservoir.production_rate = rate
        limb.esp.frequency = 50.0
    for limb in field.injectors:
        limb.well.load_state_dict(doublet.injector.state_dict())
        limb.sink.load_state_dict(doublet.sink.state_dict())
    return field


def test_two_producers_mix_into_the_supply(fresh_plant):
    """The supply carries both wells' flow at their capacity-weighted temperature."""
    field = _field(fresh_plant.doublet)
    returned = Stream(m_dot=70, T=330, p=5e6, fluid=field.producers[0].riser.fluid)
    result = field(return_in=returned)
    first = result.children["producers.0.riser"].outlets.wellhead
    second = result.children["producers.1.riser"].outlets.wellhead
    supply = result.outlets.supply_out
    assert supply.m_dot == pytest.approx(70, rel=1e-12)
    expected = (first.m_dot * first.T + second.m_dot * second.T) / (first.m_dot + second.m_dot)
    assert supply.T == pytest.approx(expected, rel=1e-12)
    assert supply.p == min(first.p, second.p)
    assert result.outputs.supply_out_T == supply.T
    assert result.children["injectors.0.well"].inlets.wellhead == returned
    leaves = result.leaves().values()
    assert result.outputs.electricity == pytest.approx(
        sum(leaf.outputs.get("electricity", 0.0) for leaf in leaves)
    )
    assert result.outputs.heat_loss == pytest.approx(
        sum(leaf.outputs.get("heat_loss", 0.0) for leaf in leaves)
    )
    audit = energy_balance(field, result)
    assert audit["relative_thermal_residual"] < 1e-12
    assert mass_balance(field, result)["relative_residual"] < 1e-12


def test_splitters_share_the_return_over_three_injectors(fresh_plant):
    """Injector i takes f_i prod (1 - f_j) of the return; the last takes the rest."""
    field = _field(fresh_plant.doublet, producers=1, injectors=3, rates=(40.0,))
    field.splitters[0].split_fraction = 0.5
    field.splitters[1].split_fraction = 0.4
    returned = Stream(m_dot=40, T=330, p=5e6, fluid=field.producers[0].riser.fluid)
    result = field(return_in=returned)
    flows = [result.children[f"injectors.{i}.well"].inlets.wellhead.m_dot for i in range(3)]
    assert flows == pytest.approx([20.0, 8.0, 12.0], rel=1e-14)
    riser = result.children["producers.0.riser"]
    assert result.outputs.supply_out_T == riser.outputs.wellhead_temperature
    assert len(field.mixers) == 0
    assert mass_balance(field, result)["relative_residual"] < 1e-12


def test_invalid_structure_raises():
    """A field needs at least one producer and one injector."""
    with pytest.raises(gm.errors.ConfigurationError, match="producers = 0"):
        generators.multi_well_spec(producers=0)
    with pytest.raises(gm.errors.ConfigurationError, match="injectors = 0"):
        generators.multi_well_spec(injectors=0)
    with pytest.raises(gm.errors.ValidationError, match="producers = 0"):
        gm.plants.from_template("MultiWellPlant", {"producers": 0})
