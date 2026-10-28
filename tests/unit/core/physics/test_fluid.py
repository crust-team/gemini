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
