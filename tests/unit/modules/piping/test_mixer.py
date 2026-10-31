"""Adiabatic mixing temperature, junction pressure, balances and limits."""

import pytest

import gemini as gm
from gemini.modules import energy_balance, mass_balance
from gemini.modules.piping import Mixer
from gemini.types import WATER, Fluid, Stream
from tests.fixtures.equivalence import assert_module_matches
from tests.fixtures.errors import raises
from tests.fixtures.reading import reading

HOT = Stream(m_dot=6, T=363.15, p=5e5)
COLD = Stream(m_dot=2, T=323.15, p=4e5)


def test_mixing_matches_hand_calculation():
    """6 kg/s at 90 C and 2 kg/s at 50 C mix to 80 C at the lower pressure."""
    result = Mixer()(branch1_in=HOT, branch2_in=COLD)
    mixed = result.outlets.fluid_out
    assert mixed.m_dot == 8 and mixed.p == 4e5
    assert mixed.T == pytest.approx(353.15, rel=1e-14)
    assert reading(result).fluid_out_T == mixed.T
    assert result.outputs.pressure_imbalance == 1e5
    assert energy_balance(Mixer(), result)["relative_residual"] < 1e-12
    assert mass_balance(Mixer(), result)["residual"] == 0


def test_zero_flows():
    """A stopped branch takes no part; a stopped junction takes the mean temperature."""
    one = Mixer()(branch1_in=HOT, branch2_in=COLD.with_(m_dot=0)).outlets.fluid_out
    assert one.T == pytest.approx(HOT.T, rel=1e-15) and one.m_dot == 6
    none = Mixer()(branch1_in=HOT.with_(m_dot=0), branch2_in=COLD.with_(m_dot=0))
    assert none.outlets.fluid_out.T == pytest.approx(343.15) and none.outlets.fluid_out.m_dot == 0
    assert energy_balance(Mixer(), none)["residual"] == 0


def test_invalid_inputs_raise():
    """Different fluids and reverse flow are rejected."""
    with raises(gm.errors.ValidationError, "invalid_design", match="expected the same fluid"):
        Mixer()(branch1_in=HOT, branch2_in=COLD.with_(fluid=WATER))
    with raises(gm.errors.ValidationError, "invalid_design"):
        Mixer()(branch1_in=HOT, branch2_in=COLD.with_(fluid=Fluid(density=1050)))
    with pytest.raises(gm.errors.PhysicsError, match="mixer: branch1_in.m_dot = -1"):
        Mixer()(branch1_in=HOT.with_(m_dot=-1), branch2_in=COLD)


def test_mixer_matches_traced():
    """Either pressure lower, unequal flows and a stopped junction trace correctly."""
    rows = [
        dict(branch1_in=Stream(m_dot=a, T=ta, p=pa), branch2_in=Stream(m_dot=b, T=tb, p=pb))
        for a, ta, pa, b, tb, pb in [
            (6, 363.15, 5e5, 2, 323.15, 4e5),
            (6, 363.15, 3e5, 2, 323.15, 4e5),
            (0, 363.15, 5e5, 2, 323.15, 4e5),
            (0, 363.15, 5e5, 0, 323.15, 4e5),
        ]
    ]
    assert_module_matches(Mixer(), rows)
