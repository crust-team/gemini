"""Constant fluid property snapshot: original defaults, mixture density and validation."""

from dataclasses import FrozenInstanceError, asdict

import numpy as np
import pytest

from gemini.errors import PhysicsRangeError
from gemini.physics.fluid import FluidProperties, mixture_density


def test_original_defaults():
    """The snapshot retains all ten properties returned by PVTConstantSTP."""
    assert asdict(FluidProperties()) == dict(
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
        with pytest.raises(PhysicsRangeError):
            FluidProperties(**override)
    with pytest.raises(FrozenInstanceError):
        FluidProperties().rho_l = 1


def test_numbers_become_floats():
    """Integer inputs are stored as ``float``."""
    assert type(FluidProperties(cp_l=3841).cp_l) is float


def test_mixture_density_is_the_snapshot_density():
    """The shared density function gives the snapshot's value, also on arrays."""
    values = FluidProperties(rho_l=1068, gmf=0.25)
    assert mixture_density(values.rho_l, values.rho_g, values.gmf) == values.density
    assert mixture_density(np.array([1000.0, 1068.0]), 1.976, 0.0).tolist() == [1000.0, 1068.0]


def test_liquid_volumetric_heat_capacity_is_density_times_heat_capacity():
    """The property multiplies in the order ``rho_l * cp_l``."""
    properties = FluidProperties(rho_l=1068.0, cp_l=3900.5)
    assert properties.liquid_volumetric_heat_capacity == 1068.0 * 3900.5
