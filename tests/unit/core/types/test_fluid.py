"""Stream dtype identity, composition and reference property models."""

import pytest
from pydantic import ValidationError

from gemini.core.physics.fluid import FluidProperties
from gemini.core.types.flows import Stream
from gemini.core.types.fluid import BRINE, GLYCOL_30, STEAM, WATER, Fluid


def test_fluid_properties_and_identity():
    """Defaults preserve all legacy numbers; overrides travel with streams and cache safely."""
    assert BRINE.properties(1e5, 300) == FluidProperties()
    brine = Fluid(liquid_density=1068, liquid_viscosity=0.00065, co2_mass_fraction=0.01)
    stream = Stream(m_dot=106.8, p=1e5, T=300, fluid=brine)
    assert stream.volumetric_flow() == pytest.approx(0.1)
    assert stream.with_(T=310).fluid == brine
    assert brine.properties(1e5, 300) is brine.properties(2e5, 350)
    assert WATER != BRINE
    assert GLYCOL_30.properties(1e5, 313.15) == FluidProperties(
        rho_l=1029.85, cp_l=3841, k_l=0.4622, mu_l=0.0016295
    )
    assert Fluid(gas_mass_fraction=0.1, specific_heat=4000).properties(1e5, 300) == (
        FluidProperties(gmf=0.1, cp_l=4000)
    )
    assert Stream.model_validate_json(stream.model_dump_json()) == stream
    with pytest.raises(ValidationError):
        brine.salinity = 0.5
    with pytest.raises(ValidationError):
        Fluid(salinity=0.9, co2_mass_fraction=0.2)
    with pytest.raises(ValidationError):
        Stream(m_dot=1, T=300, p=1e5, fluid="brine")


def test_steam_kind_labels_vapour_without_changing_other_fluids():
    """``steam`` is a distinct, serialisable label; it keeps the default constant snapshot."""
    assert STEAM == Fluid(kind="steam") and STEAM not in (BRINE, WATER)
    assert STEAM.properties(6e5, 432) == FluidProperties()
    stream = Stream(m_dot=20, T=432, p=6e5, fluid=STEAM)
    assert Stream.model_validate_json(stream.model_dump_json()).fluid.kind == "steam"
    assert BRINE.kind == "brine" and WATER.kind == "water"


def test_corrosion_composition_conversion():
    """Dissolved mass fraction is converted through Henry law, never used as gas mole fraction."""
    from gemini.core.physics.chemistry import henry_constant

    fluid = Fluid(salinity=0.07, co2_mass_fraction=0.001, liquid_density=1068)
    values = fluid.corrosion_inputs(1e6, 300)
    assert values["ionic_strength"] == pytest.approx(74.76)
    assert values["co2_partial_pressure"] * henry_constant(300) == pytest.approx(1.068 / 0.04401)
