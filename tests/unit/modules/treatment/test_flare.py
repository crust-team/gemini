"""The flare burns its inlet and reports what its composition gives."""

import pytest

import gemini as gm
from gemini.errors import PhysicsError
from gemini.modules import Flare
from gemini.physics import combustion, gas
from tests.fixtures.equivalence import assert_module_matches

COMPOSITION = {"CH4": 0.8, "CO2": 0.2}
FLUID = gm.Fluid(kind="gas", gas_composition=COMPOSITION)


def stream(flow):
    """Return a gas stream of ``flow`` [kg/s]."""
    return gm.Stream(m_dot=flow, T=330, p=2e5, fluid=FLUID)


def test_emissions_come_from_the_composition():
    """Carried CO2 plus 98 % of the formed CO2, and 2 % of the methane unburnt."""
    out = Flare()(fluid_in=stream(0.1)).outputs
    efficiency = combustion.FLARE_EFFICIENCY
    carried, formed = gas.mass_fraction(COMPOSITION, "CO2"), gas.combustion_co2(COMPOSITION)
    assert out.co2_emission == pytest.approx(0.1 * (carried + efficiency * formed))
    assert out.methane_emission == pytest.approx(
        0.1 * gas.mass_fraction(COMPOSITION, "CH4") * (1 - efficiency)
    )
    assert out.burned_mass_flow == 0.1


def test_a_stream_without_a_composition_emits_nothing():
    """Nothing is known about the gas, so nothing is reported."""
    assert Flare()(fluid_in=gm.Stream(m_dot=0.1, T=330, p=2e5)).outputs.co2_emission == 0


def test_reverse_flow_is_refused():
    """A flare only burns."""
    with pytest.raises(PhysicsError):
        Flare()(fluid_in=stream(-0.1))


def test_traced_call_matches_one_call_per_row():
    """No gas and some gas equal one call per row."""
    assert_module_matches(Flare(), [dict(fluid_in=stream(flow)) for flow in (0.0, 0.1, 1.0)])
