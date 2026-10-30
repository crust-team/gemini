"""Vent and flare emissions, combustion energy and conservation inside a plant."""

import pytest

import gemini as gm
from gemini.modules import Module
from gemini.modules.balance import energy_balance, mass_balance
from gemini.modules.treatment import Degasser, Vent
from gemini.physics import constants
from gemini.types import Fluid, Inlet, Outlet, Stream
from tests.fixtures.equivalence import assert_module_matches

GAS = Stream(m_dot=0.2, T=330, p=1.2e5)


class GasDisposal(Module):
    """Degas a brine and dispose of the separated gas."""

    def __init__(self):
        """Declare the degasser, the vent and the plant ports."""
        super().__init__()

        # Modules
        self.degasser = Degasser().update_params(separation_efficiency=0.9)
        self.vent = Vent().update_params(mode="flare", co2_mass_fraction=0.9)

        # Inlets
        self.inlet = Inlet(Stream)

        # Outlets
        self.liquid = Outlet(Stream)

    def forward(self, inlets):
        """Separate, then flare the gas."""

        # Modules
        degassed = self.degasser(inlet=inlets.inlet)
        self.vent(inlet=degassed.outlets.gas)

        # Outlets
        liquid = degassed.outlets.liquid

        outlets = dict(liquid=liquid)
        return outlets


def vent(mode):
    """Return a vent for a 90 % CO2, 5 % methane gas."""
    return Vent().update_params(mode=mode, co2_mass_fraction=0.9, methane_mass_fraction=0.05)


def test_venting_releases_the_gas_unburnt():
    """Venting emits the gas's CO2 and methane and uses no fuel."""
    module = vent("vent")
    result = module(inlet=GAS)
    out = result.outputs
    assert out.vented_mass_flow == 0.2 and result.outlets.outlet == GAS
    assert out.co2_emission == pytest.approx(0.18)
    assert out.methane_emission == pytest.approx(0.01)
    assert out.fuel == out.heat_loss == 0
    assert mass_balance(module, result)["residual"] == 0
    assert energy_balance(module, result)["relative_residual"] < 1e-12


def test_flaring_burns_methane_to_co2_and_heat():
    """Flaring at 98 % converts methane to CO2 and releases its heating value as heat loss."""
    module = vent("flare")
    result = module(inlet=GAS)
    out = result.outputs
    burnt = 0.98 * 0.01
    assert out.co2_emission == pytest.approx(0.18 + burnt * constants.CO2_MOLAR_MASS / 0.016043)
    assert out.methane_emission == pytest.approx(0.01 - burnt)
    assert out.fuel == pytest.approx(burnt * 50.0e6) and out.heat_loss == out.fuel
    assert mass_balance(module, result)["residual"] == 0
    assert energy_balance(module, result)["relative_residual"] < 1e-12


def test_limits():
    """Zero flow emits nothing; reverse flow and an impossible composition raise."""
    module = vent("flare")
    assert module(inlet=GAS.with_(m_dot=0)).outputs.co2_emission == 0
    with pytest.raises(gm.errors.PhysicsRangeError, match="inlet.m_dot"):
        module(inlet=GAS.with_(m_dot=-0.1))
    module.update_params(methane_mass_fraction=0.2)
    with pytest.raises(gm.errors.ConfigurationError, match="expected at most 1"):
        module(inlet=GAS)


def test_degassed_gas_leaves_the_plant_through_the_vent():
    """Free gas separated by the degasser is flared; plant mass and energy close."""
    plant = GasDisposal()
    inlet = Stream(m_dot=10, T=350, p=1e6, fluid=Fluid(gas_mass_fraction=0.01))
    result = plant(inlet=inlet)
    vented = result.children["vent"].outputs
    assert vented.vented_mass_flow == pytest.approx(0.09)
    assert vented.co2_emission == pytest.approx(0.081)
    assert mass_balance(plant, result)["relative_residual"] < 1e-15
    assert energy_balance(plant, result)["relative_residual"] < 1e-12


def test_vent_matches_traced():
    """Vent and flare emissions trace and equal one call per row."""
    rows = [dict(inlet=Stream(m_dot=m_dot, T=330, p=1.2e5)) for m_dot in (0, 0.2, 1.5)]
    for mode in ("vent", "flare"):
        assert_module_matches(
            Vent().update_params(mode=mode, co2_mass_fraction=0.9, methane_mass_fraction=0.05),
            rows,
        )
