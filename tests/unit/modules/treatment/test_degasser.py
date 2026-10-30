"""Degasser free-gas separation, pressure loss and conservation."""

import pytest

from gemini.modules.balance import energy_balance, mass_balance
from gemini.modules.treatment import Degasser
from gemini.types import Fluid
from gemini.types.flows import Stream
from tests.fixtures.equivalence import assert_module_matches

GASSY = Fluid(gas_mass_fraction=0.02)


def test_equipment_forward():
    """Equipment preserves mass and valid pressure/temperature."""
    c = Degasser().update_params(heat_transfer_coeff=100000)
    result = c(inlet=Stream(m_dot=1, T=300, p=1e6))
    assert sum(s.m_dot for s in result.outlets.values() if isinstance(s, Stream)) == 1
    assert result.outlets["liquid"].T == 300
    assert result.outlets["liquid"].p >= 0


def test_default_reproduces_the_liquid_only_model_for_any_fluid():
    """Zero default efficiency: no gas, liquid unchanged except the 0.149 bar loss."""
    inlet = Stream(m_dot=40, T=350, p=1e6, fluid=GASSY)
    result = Degasser()(inlet=inlet)
    assert result.outlets.liquid == inlet.with_(p=1e6 - 14900)
    assert result.outlets.gas == inlet.with_(p=1e6 - 14900, m_dot=0)
    assert result.outputs.gas_mass_flow == 0
    assert result.outputs.pressure_drop == 14900


def test_separation_conserves_gas_mass_and_energy():
    """The separated share of the free gas leaves through gas; the rest stays in the liquid."""
    degasser = Degasser().update_params(separation_efficiency=0.75, p_out=2e5)
    inlet = Stream(m_dot=10, T=350, p=1e6, fluid=GASSY)
    result = degasser(inlet=inlet)
    liquid, gas = result.outlets.liquid, result.outlets.gas
    assert gas.m_dot == pytest.approx(0.75 * 0.02 * 10)
    assert liquid.m_dot == pytest.approx(10 - 0.15)
    assert liquid.fluid.gas_mass_fraction == pytest.approx(0.005 / 0.985)
    assert liquid.m_dot * liquid.fluid.gas_mass_fraction == pytest.approx(0.25 * 0.02 * 10)
    assert liquid.p == gas.p == 2e5 and liquid.T == gas.T == 350
    assert result.outputs.gas_mass_flow == gas.m_dot
    assert result.outputs.pressure_drop == 8e5
    assert mass_balance(degasser, result)["residual"] == 0
    assert energy_balance(degasser, result)["relative_residual"] < 1e-12


def test_full_efficiency_and_zero_flow():
    """Perfect separation leaves a gas-free liquid; zero flow separates nothing."""
    degasser = Degasser().update_params(separation_efficiency=1)
    result = degasser(inlet=Stream(m_dot=5, T=350, p=1e6, fluid=GASSY))
    assert result.outlets.liquid.fluid.gas_mass_fraction == 0
    assert result.outlets.gas.m_dot == pytest.approx(0.1)
    stopped = degasser(inlet=Stream(m_dot=0, T=350, p=1e6, fluid=GASSY))
    assert stopped.outlets.gas.m_dot == 0 and stopped.outlets.liquid.m_dot == 0


def test_degasser_matches_traced():
    """The split traces for a gassy fluid, a gas-free fluid and a set vessel pressure."""
    for fluid in (GASSY, Fluid()):
        for settings in (dict(separation_efficiency=0.75), dict(p_out=2e5)):
            module = Degasser().update_params(**settings)
            rows = [
                dict(inlet=Stream(m_dot=m_dot, T=350, p=1e6, fluid=fluid)) for m_dot in (0, 1, 10)
            ]
            assert_module_matches(module, rows)
