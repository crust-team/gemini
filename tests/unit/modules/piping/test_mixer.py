"""Adiabatic mixing temperature, junction pressure, balances and limits."""

import pytest

import gemini as gm
from gemini.modules import energy_balance, mass_balance
from gemini.modules.piping import Mixer
from gemini.types import WATER, Fluid, Stream
from tests.fixtures.equivalence import assert_module_matches
from tests.fixtures.errors import raises

HOT = Stream(m_dot=6, T=363.15, p=5e5)
COLD = Stream(m_dot=2, T=323.15, p=4e5)


def test_mixing_matches_hand_calculation():
    """6 kg/s at 90 C and 2 kg/s at 50 C mix to 80 C at the lower pressure."""
    result = Mixer()(first_in=HOT, second_in=COLD)
    mixed = result.outlets.mixed_out
    assert mixed.m_dot == 8 and mixed.p == 4e5
    assert mixed.T == pytest.approx(353.15, rel=1e-14)
    assert result.outputs.mixed_out_T == mixed.T
    assert result.outputs.pressure_imbalance == 1e5
    assert energy_balance(Mixer(), result)["relative_residual"] < 1e-12
    assert mass_balance(Mixer(), result)["residual"] == 0


def test_zero_flows():
    """A stopped branch takes no part; a stopped junction takes the mean temperature."""
    one = Mixer()(first_in=HOT, second_in=COLD.with_(m_dot=0)).outlets.mixed_out
    assert one.T == pytest.approx(HOT.T, rel=1e-15) and one.m_dot == 6
    none = Mixer()(first_in=HOT.with_(m_dot=0), second_in=COLD.with_(m_dot=0))
    assert none.outlets.mixed_out.T == pytest.approx(343.15) and none.outlets.mixed_out.m_dot == 0
    assert energy_balance(Mixer(), none)["residual"] == 0


def test_invalid_inputs_raise():
    """Different fluids and reverse flow are rejected."""
    with raises(gm.errors.ValidationError, "invalid_design", match="expected the same fluid"):
        Mixer()(first_in=HOT, second_in=COLD.with_(fluid=WATER))
    with raises(gm.errors.ValidationError, "invalid_design"):
        Mixer()(first_in=HOT, second_in=COLD.with_(fluid=Fluid(liquid_density=1050)))
    with pytest.raises(gm.errors.PhysicsError, match="mixer: first_in.m_dot = -1"):
        Mixer()(first_in=HOT.with_(m_dot=-1), second_in=COLD)


def test_mixer_matches_traced():
    """Either pressure lower, unequal flows and a stopped junction trace correctly."""
    rows = [
        dict(first_in=Stream(m_dot=a, T=ta, p=pa), second_in=Stream(m_dot=b, T=tb, p=pb))
        for a, ta, pa, b, tb, pb in [
            (6, 363.15, 5e5, 2, 323.15, 4e5),
            (6, 363.15, 3e5, 2, 323.15, 4e5),
            (0, 363.15, 5e5, 2, 323.15, 4e5),
            (0, 363.15, 5e5, 0, 323.15, 4e5),
        ]
    ]
    assert_module_matches(Mixer(), rows)
