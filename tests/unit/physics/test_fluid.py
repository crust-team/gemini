"""Constant fluid property snapshot: original defaults, mixture density and validation."""

from dataclasses import FrozenInstanceError, asdict

import numpy as np
import pytest

from gemini.errors import PhysicsRangeError
from gemini.physics.fluid import (
    DEFAULT_LIQUID_DENSITY,
    FluidProperties,
    heat_capacity_rate,
    liquid_volume_flow,
    mixture_density,
    volume_flow,
)
from tests.fixtures.equivalence import assert_function_matches


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


def test_volume_flow_and_liquid_volume_flow_by_hand():
    """Volume flow is m / rho; the liquid of 10 kg/s at x = 0.2 and 1000 kg/m3 is 8 l/s."""
    assert volume_flow(10.0, 1000.0) == 0.01
    assert liquid_volume_flow(10.0, 0.2, 1000.0) == pytest.approx(0.008)
    assert liquid_volume_flow(10.0, 0.0, 1000.0) == volume_flow(10.0, 1000.0)


def test_heat_capacity_rate_by_hand():
    """C = m cp: 10 kg/s of water at 4217.4 J/kg/K carries 42174 W/K, sign kept."""
    assert heat_capacity_rate(10.0, 4217.4) == pytest.approx(42174.0)
    assert heat_capacity_rate(-10.0, 4217.4) == pytest.approx(-42174.0)


def test_flow_functions_match_on_arrays():
    """The flow functions and the mixture density run on arrays as on floats."""
    assert_function_matches(volume_flow, [(10.0, 1000.0), (-3.0, 850.0), (0.0, 1.9)])
    assert_function_matches(liquid_volume_flow, [(10.0, 0.2, 1000.0), (-3.0, 0.0, 850.0)])
    assert_function_matches(heat_capacity_rate, [(10.0, 4217.4), (-3.0, 819.0), (0.0, 1.0)])
    assert_function_matches(mixture_density, [(1000.0, 1.976, 0.0), (1000.0, 1.976, 0.5)])


def test_default_liquid_density_is_the_snapshot_default():
    """The named default is the density of the snapshot and of the corrosion default."""
    assert FluidProperties().rho_l == DEFAULT_LIQUID_DENSITY == 1000.0
