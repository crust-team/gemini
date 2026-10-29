"""Doublet breakthrough, ground conduction shapes and Ramey wellbore relations."""

import math

import numpy as np
import pytest
from scipy.special import exp1

from gemini.core.physics import ground
from gemini.errors import PhysicsRangeError


def test_aquifer_heat_capacity_and_breakthrough_volume():
    """The mixing rule weights by porosity; V_B is pi L**2 H (rho c)_a / (3 (rho c)_w)."""
    aquifer = ground.aquifer_volumetric_heat_capacity(0.2, 4.2e6, 2.5e6)
    assert aquifer == pytest.approx(0.2 * 4.2e6 + 0.8 * 2.5e6)
    volume = ground.doublet_breakthrough_volume(1000, 50, aquifer, 4.2e6)
    assert volume == pytest.approx(math.pi * 1000**2 * 50 * aquifer / (3 * 4.2e6))
    with pytest.raises(PhysicsRangeError, match="porosity = 1.5"):
        ground.aquifer_volumetric_heat_capacity(1.5, 4.2e6, 2.5e6)
    with pytest.raises(PhysicsRangeError, match="well_spacing = 0"):
        ground.doublet_breakthrough_volume(0, 50, aquifer, 4.2e6)


def test_doublet_cold_fraction_follows_the_dipole_travel_times():
    """No cold water before breakthrough; half the flow is cold at three breakthrough volumes."""
    assert ground.doublet_cold_fraction(0) == ground.doublet_cold_fraction(1) == 0
    assert ground.doublet_cold_fraction(3) == pytest.approx(0.5, abs=1e-12)
    theta = 1.0
    ratio = 3 * (math.sin(theta) - theta * math.cos(theta)) / math.sin(theta) ** 3
    assert ground.doublet_cold_fraction(ratio) == pytest.approx(theta / math.pi, abs=1e-12)
    small = 1 + 1e-8
    assert ground.doublet_cold_fraction(small) == pytest.approx(
        math.sqrt(5 * 1e-8 / 2) / math.pi, rel=1e-6
    )
    fractions = [ground.doublet_cold_fraction(r) for r in (1.01, 1.5, 4, 100, 1e6)]
    assert fractions == sorted(fractions) and fractions[-1] < 1
    assert ground.doublet_cold_fraction(1e300) == 1
    with pytest.raises(PhysicsRangeError, match="volume_ratio = -1"):
        ground.doublet_cold_fraction(-1)


def test_series_and_direct_travel_times_agree_at_the_switch():
    """The small-angle series matches the closed form where the implementation switches."""
    theta = 0.1
    direct = 3 * (math.sin(theta) - theta * math.cos(theta)) / math.sin(theta) ** 3
    assert ground._dipole_travel_time(theta * (1 - 1e-12)) == pytest.approx(direct, rel=1e-12)


def test_store_and_field_conductances():
    """The store conductance uses its whole envelope; the field uses the cylinder shape factor."""
    radius = math.sqrt(1e5 / (math.pi * 20))
    area = 2 * math.pi * radius * (radius + 20)
    expected = 2 * 2.5 * area / math.sqrt(math.pi * 1e-6 * 1.5e7)
    assert ground.cylinder_store_conductance(2.5, 1e-6, 1e5, 20, 1.5e7) == pytest.approx(expected)
    assert ground.cylinder_store_conductance(2.5, 1e-6, 0, 20, 1.5e7) == 0
    assert ground.vertical_cylinder_conductance(2, 150, 20) == pytest.approx(
        2 * 2 * math.pi * 150 / math.log(30)
    )
    with pytest.raises(PhysicsRangeError, match="volume = -1"):
        ground.cylinder_store_conductance(2.5, 1e-6, -1, 20, 1.5e7)
    with pytest.raises(PhysicsRangeError, match="expected ln"):
        ground.vertical_cylinder_conductance(2, 10, 40)


def test_steady_flux_resistance_matches_the_annulus_solution():
    """The closed form equals the integrated uniform-sink annulus profile and Hellstrom's limit."""
    k, r_b, r_e, sink = 2.0, 0.075, 3.0, 1.0
    r = np.linspace(r_b, r_e, 200001)
    rise = sink / (2 * k) * (r_e**2 * np.log(r / r_b) - (r**2 - r_b**2) / 2)
    weights = 2 * np.pi * r
    mean = np.sum((rise[1:] * weights[1:] + rise[:-1] * weights[:-1]) / 2 * np.diff(r))
    mean /= np.pi * (r_e**2 - r_b**2)
    heat = sink * np.pi * (r_e**2 - r_b**2)
    assert ground.steady_flux_resistance(k, r_b, r_e) == pytest.approx(mean / heat, rel=1e-8)
    limit = (math.log(1e4) - 0.75) / (2 * math.pi * k)
    assert ground.steady_flux_resistance(k, 1e-4, 1) == pytest.approx(limit, rel=1e-7)
    with pytest.raises(PhysicsRangeError, match="cell_radius = 0.05"):
        ground.steady_flux_resistance(k, r_b, 0.05)


def test_ramey_time_function_is_the_line_source_asymptote():
    """At long times f(t) equals half the exponential integral; short times are rejected."""
    time, diffusivity, radius = 3.15e7, 1e-6, 0.1
    exact = exp1(radius**2 / (4 * diffusivity * time)) / 2
    assert ground.ramey_time_function(time, diffusivity, radius) == pytest.approx(exact, rel=1e-4)
    fourier = ground.MIN_RAMEY_FOURIER
    short = ground.ramey_time_function(fourier * radius**2 / diffusivity, diffusivity, radius)
    assert short == pytest.approx(exp1(1 / (4 * fourier)) / 2, rel=0.01)
    with pytest.raises(PhysicsRangeError, match="alpha t / r"):
        ground.ramey_time_function(3600, diffusivity, radius)
    with pytest.raises(PhysicsRangeError, match="time = 0"):
        ground.ramey_time_function(0, diffusivity, radius)


def test_ramey_fluid_temperature_solves_the_energy_balance():
    """The profile satisfies dT/dz = (T_rock - T) / A and starts at the inlet temperature."""
    args = dict(inlet_temperature=300, top_temperature=283, gradient=0.03, relaxation_length=800)
    assert ground.ramey_fluid_temperature(length=0, **args) == 300
    depth, step = 1500.0, 1e-3
    slope = (
        ground.ramey_fluid_temperature(length=depth + step, **args)
        - ground.ramey_fluid_temperature(length=depth - step, **args)
    ) / (2 * step)
    temperature = ground.ramey_fluid_temperature(length=depth, **args)
    assert slope == pytest.approx((283 + 0.03 * depth - temperature) / 800, rel=1e-6)
    far = ground.ramey_fluid_temperature(length=1e6, **args)
    assert far == pytest.approx(283 + 0.03 * 1e6 - 0.03 * 800)
    with pytest.raises(PhysicsRangeError, match="length = -1"):
        ground.ramey_fluid_temperature(length=-1, **args)
    with pytest.raises(PhysicsRangeError, match="relaxation_length = 0"):
        ground.ramey_fluid_temperature(**(args | {"relaxation_length": 0}), length=10)
