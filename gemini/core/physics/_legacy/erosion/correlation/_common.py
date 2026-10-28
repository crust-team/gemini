"""Shared helpers for erosion correlations (DNV, OKA, E/CRC Tulsa)."""

import math


def mass_flow_and_velocity(flow_rate_m3h, rho_fluid_kgm3, diameter_m):
    """Particle mass flow, pipe area, and mixture velocity from volumetric flow.

    Parameters
    ----------
    flow_rate_m3h: float
        Fluid flow rate (m3/h).
    rho_fluid_kgm3: float
        Mixture density of fluid (kg/m3).
    diameter_m: float
        Inner diameter of the pipe (m).

    Returns
    -------
    tuple
        ``(mp_kgs, up_ms, a_pipe_m2)`` -- particle mass flow [kg/s],
        mixture impact velocity [m/s], pipe cross-section area [m2].
    """
    # -- mass flow of particles [kg/s] ----------------------------------
    mp_kgs = flow_rate_m3h * rho_fluid_kgm3 / 3600

    # -- pipe cross-section + mixture velocity --------------------------
    a_pipe_m2 = 0.25 * math.pi * diameter_m**2
    up_ms = mp_kgs / (rho_fluid_kgm3 * a_pipe_m2)

    return mp_kgs, up_ms, a_pipe_m2
