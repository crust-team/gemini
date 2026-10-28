"""Original constant-water defaults and override validation."""

import pytest
from pydantic import ValidationError

from gemini.core.physics.fluid import ConstantWater


def test_original_defaults_and_overrides():
    """The new API retains all ten properties returned by PVTConstantSTP."""
    props = ConstantWater().properties(100000, 288.15)
    assert props.model_dump() == dict(
        rho_g=1.976,
        rho_l=1000,
        gmf=0,
        mu_g=21.29e-6,
        mu_l=0.001,
        cp_g=819,
        cp_l=4217.4,
        k_g=0.0147,
        k_l=1.6,
        sigma=0.0728,
    )
    assert ConstantWater(RHOL=1068, VISL=0.00065).properties(1, 300).mu_l == 0.00065
    with pytest.raises(ValidationError):
        ConstantWater(RHOL=-1)


def test_named_fluid_preserves_stream_density():
    """A configured brine factory gives streams the same density as equipment calculations."""
    from functools import partial

    from gemini.core.physics import fluid
    from gemini.core.types.flows import Stream

    fluid.register_fluid("test_brine", partial(ConstantWater, RHOL=1068))
    stream = Stream(m_dot=106.8, p=1e5, T=300, fluid="test_brine")
    assert stream.volumetric_flow() == pytest.approx(0.1)
    with pytest.raises(ValueError, match="Cannot replace"):
        fluid.register_fluid("water", ConstantWater)
