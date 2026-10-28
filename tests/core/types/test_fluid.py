"""Stream dtype identity, composition and reference property models."""

import pytest
from pydantic import ValidationError

from gemini.core.physics.fluid import ConstantWater
from gemini.core.types.flows import Stream
from gemini.core.types.fluid import BRINE, GLYCOL_30, WATER, Fluid


def test_fluid_properties_and_identity():
    """Defaults preserve all legacy numbers; overrides travel with streams and cache safely."""
    assert BRINE.properties(1e5, 300) == ConstantWater().properties(1e5, 300)
    brine = Fluid(liquid_density=1068, liquid_viscosity=0.00065, co2_mass_fraction=0.01)
    stream = Stream(m_dot=106.8, p=1e5, T=300, fluid=brine)
    assert stream.volumetric_flow() == pytest.approx(0.1)
    assert stream.with_(T=310).fluid == brine
    assert brine.properties(1e5, 300) is brine.properties(2e5, 350)
    assert WATER != BRINE
    assert GLYCOL_30.properties(1e5, 313.15).cp_l == 3841
    assert Stream.model_validate_json(stream.model_dump_json()) == stream
    with pytest.raises(ValidationError):
        brine.salinity = 0.5
    with pytest.raises(ValidationError):
        Fluid(salinity=0.9, co2_mass_fraction=0.2)
    with pytest.raises(ValidationError):
        Stream(m_dot=1, T=300, p=1e5, fluid="brine")
