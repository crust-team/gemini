"""Constant fluid property snapshot: original defaults, mixture density and validation."""

import pytest
from pydantic import ValidationError

from gemini.core.physics.fluid import FluidProperties


def test_original_defaults():
    """The snapshot retains all ten properties returned by PVTConstantSTP."""
    assert FluidProperties().model_dump() == dict(
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


def test_mixture_density_and_validation():
    """Density is the homogeneous mixture; impossible properties are rejected."""
    assert FluidProperties(rho_l=1068).density == 1068
    assert FluidProperties(gmf=0.5).density == pytest.approx(1 / (0.5 / 1.976 + 0.5 / 1000))
    for override in ({"rho_l": -1}, {"gmf": 1}, {"mu_l": 0}):
        with pytest.raises(ValidationError):
            FluidProperties(**override)
    with pytest.raises(ValidationError):
        FluidProperties().rho_l = 1
