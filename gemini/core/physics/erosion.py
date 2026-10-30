"""Erosion correlations: DNV RP O501, OKA, E/CRC Tulsa and API RP 14E.

The penetration-rate correlations work in their published basis: impact angle in degrees,
flow in m3/h, Vickers hardness in GPa and OKA particle diameter in mm. ``erosion_rate`` is the
SI boundary and returns mm/year, the explicit literature-unit exception of the package.
"""

import math

from gemini import ops
from gemini.errors import PhysicsRangeError, UnknownCorrelationError
from gemini.utils.strings import did_you_mean, join_names

from . import geometry, units

_API_C_FACTOR = 125
"""API RP 14E empirical constant C in the historical imperial basis."""

_GPA_PER_HV = 0.009807
"""GPa per Vickers hardness number, from http://www.iron-foundry.com/castings-hardness.html."""

_DNV_MATERIALS = {
    "steel": (2e-9, 2.6, 7800),
    "grp/epoxy": (0.3e-9, 3.6, 1800),
    "grp/vinyl ester": (0.6e-9, 3.6, 1800),
}
"""DNV RP O501 material constant K, velocity exponent n and pipe density [kg/m3].

Names match case-insensitively. Titanium (K = 2e-9, n = 2.6, 4500 kg/m3) is listed by DNV
but stays rejected: the original compared ``material.upper() == "titanium"``, which can never
be true.
"""

_OKA_PARTICLES = {
    "SIO2": (104, 326, -0.12, lambda hardness: 2.3 * ops.pow(hardness, 0.038), 0.19, 65),
    "SIC": (99, 326, -0.05, lambda hardness: 3 * ops.pow(hardness, 0.085), 0.19, 45),
    "GLASS": (100, 200, -0.16, lambda hardness: 2.1, 0.19, 27),
}
"""OKA particle constants: reference velocity [m/s], reference diameter, k1, k2(Hv), k3, K.

Names match case-insensitively (SiO2 sand, SiC, glass beads).
"""

_MODELS = {
    "DNV": "DNV",
    "DNVGL": "DNV",
    "OKA": "OKA",
    "TULSA": "TULSA",
    "E/CRC TULSA": "TULSA",
    "ECRC": "TULSA",
    "API": "API",
}
"""Accepted model spellings (upper-cased, stripped) and their correlation."""


def _particle_flow(flow_rate_m3h, rho_fluid, diameter):
    """Return particle mass flow [kg/s], impact velocity [m/s] and pipe area [m2].

    NOTE(refactor): particle mass flow equals the total fluid mass flow; there is no solids
    fraction.
    """
    particle_mass_flow = units.kgh_to_kgs(flow_rate_m3h * rho_fluid)
    area = geometry.circle_area(diameter)
    velocity = particle_mass_flow / (rho_fluid * area)
    return particle_mass_flow, velocity, area


def _dnv_rate(alpha_deg, material, rho_fluid, diameter, flow_rate_m3h):
    """Return the DNV RP O501 erosion rate [mm/year].

    Source: https://wiki.pengtools.com/images/9/91/RP_O501_EROSIVE_WEAR_IN_PIPING_SYSTEMS.pdf
    """
    if material.lower() not in _DNV_MATERIALS:
        raise UnknownCorrelationError(
            f"erosion_rate DNV: material = {material!r}; expected one of "
            f"{join_names(_DNV_MATERIALS)}{did_you_mean(material.lower(), _DNV_MATERIALS)}"
        )
    constant, exponent, rho_pipe = _DNV_MATERIALS[material.lower()]
    mass_flow, velocity, area = _particle_flow(flow_rate_m3h, rho_fluid, diameter)
    angle = units.deg_to_rad(alpha_deg)
    angle_function = angle * (
        9.37
        + angle
        * (
            -42.295
            + angle
            * (
                110.864
                + angle
                * (
                    -175.804
                    + angle * (170.137 + angle * (-98.398 + angle * (31.211 - 4.17 * angle)))
                )
            )
        )
    )
    impact_area = area / ops.sin(angle)
    return (
        units.ms_to_mm_year(1)
        * mass_flow
        * constant
        * ops.pow(velocity, exponent)
        * angle_function
        / (rho_pipe * impact_area)
    )


def _oka_rate(
    alpha_deg,
    particle_material,
    hardness_gpa,
    particle_diameter_mm,
    rho_fluid,
    diameter,
    flow_rate_m3h,
):
    """Return the OKA erosion rate [mm/year].

    Source: https://www.sciencedirect.com/science/article/pii/S0043164805000979

    NOTE(refactor): OKA documents the particle diameter in mm; it is retained despite the
    reference diameter 326.
    """
    key = particle_material.upper()
    if key not in _OKA_PARTICLES:
        raise UnknownCorrelationError(
            f"erosion_rate OKA: particle_material = {particle_material!r}; expected one of "
            f"{join_names(_OKA_PARTICLES)}{did_you_mean(key, _OKA_PARTICLES)}"
        )
    reference_velocity, reference_diameter, k1, k2, k3, constant = _OKA_PARTICLES[key]
    mass_flow, velocity, area = _particle_flow(flow_rate_m3h, rho_fluid, diameter)
    angle = units.deg_to_rad(alpha_deg)
    impact_area = units.m2_to_mm2(area) / ops.sin(angle)
    erosion_per_mass = (
        constant
        * ops.pow(hardness_gpa, k1)
        * ops.pow(velocity / reference_velocity, k2(hardness_gpa))
        * ops.pow(particle_diameter_mm / reference_diameter, k3)
    )
    return units.SECONDS_PER_YEAR * mass_flow / impact_area * erosion_per_mass


def _tulsa_rate(
    alpha_deg, hardness_gpa, shape_factor, rho_pipe, rho_fluid, diameter, flow_rate_m3h
):
    """Return the E/CRC Tulsa erosion rate [mm/year].

    Source: http://www.ecrc.utulsa.edu/. Brinell hardness follows from Vickers hardness as
    0.95057 Hv - 0.03743 (http://www.iron-foundry.com/castings-hardness.html).
    """
    mass_flow, velocity, area = _particle_flow(flow_rate_m3h, rho_fluid, diameter)
    angle = units.deg_to_rad(alpha_deg)
    angle_function = (
        5.4 * angle - 10.11 * angle**2 + 10.93 * angle**3 - 6.33 * angle**4 + 1.42 * angle**5
    )
    impact_area = area / ops.sin(angle)
    brinell = hardness_gpa / _GPA_PER_HV * 0.95057 - 0.03743
    erosion_per_mass = (
        2.17e-7 * ops.pow(brinell, -0.59) * shape_factor * ops.pow(velocity, 2.41) * angle_function
    )
    return units.ms_to_mm_year(1) * erosion_per_mass * mass_flow / (rho_pipe * impact_area)


def _particle_model_rate(name, alpha_deg, hardness_gpa, particle, pipe, flow):
    """Return the OKA or Tulsa rate [mm/year] for the shared ``erosion_rate`` conditions."""
    particle_material, particle_diameter = particle
    shape_factor, rho_pipe = pipe
    if name == "OKA":
        millimetres = units.m_to_mm(particle_diameter)
        return _oka_rate(alpha_deg, particle_material, hardness_gpa, millimetres, *flow)
    return _tulsa_rate(alpha_deg, hardness_gpa, shape_factor, rho_pipe, *flow)


def erosion_rate(
    model: str,
    *,
    flow_rate: float,
    rho_fluid: float,
    diameter: float,
    alpha: float = math.pi / 2,
    material: str = "steel",
    hardness: float = 1e9,
    particle_material: str = "SIO2",
    particle_diameter: float = 0.0001,
    rho_pipe: float = 7800,
    shape_factor: float = 0.5,
) -> float:
    """Return erosion rate [mm/year] from the original DNV, OKA or Tulsa correlation.

    Parameters
    ----------
    model : str
        DNV, OKA or TULSA, case-insensitive, also as DNVGL, E/CRC Tulsa or ECRC.
    flow_rate, rho_fluid, diameter : float
        Volume flow [m3/s], density [kg/m3], internal diameter [m]. A negative flow raises
        wherever it makes a velocity power complex.
    alpha, material, hardness : float, str, float
        Nonzero impact angle [rad], pipe material [-], Vickers hardness [Pa].
    particle_material, particle_diameter : str, float
        Particle material [-] and diameter [m].
    rho_pipe, shape_factor : float
        Pipe density [kg/m3] and particle shape factor [-].

    Returns
    -------
    float
        Erosion rate [mm/year]. API is available separately as a velocity limit.

    Notes
    -----
    The impact angle is converted to degrees at this boundary and back to radians inside the
    correlations; the rad→deg→rad round trip changes the last bits and is retained.
    """
    name = _MODELS.get(str(model).strip().upper())
    if name is None or name == "API":
        raise UnknownCorrelationError(
            f"erosion_rate: model = {model!r}; expected DNV, OKA or TULSA"
            + ("; API is a velocity limit, use api_erosional_velocity" if name else "")
        )
    ops.check(
        ops.ne(alpha, 0),
        PhysicsRangeError,
        "erosion_rate: alpha = {alpha} rad; expected a nonzero angle",
        alpha=alpha,
    )
    flow_rate_m3h, alpha_deg = units.m3s_to_m3h(flow_rate), units.rad_to_deg(alpha)
    if name == "DNV":
        rate = _dnv_rate(alpha_deg, material, rho_fluid, diameter, flow_rate_m3h)
    else:
        hardness_gpa = units.pa_to_gpa(hardness)
        rate = _particle_model_rate(
            name,
            alpha_deg,
            hardness_gpa,
            (particle_material, particle_diameter),
            (shape_factor, rho_pipe),
            (rho_fluid, diameter, flow_rate_m3h),
        )
    ops.check(
        ops.logical_not(ops.isnan(rate)),
        PhysicsRangeError,
        "erosion_rate {name}: flow_rate = {flow_rate} m3/s gives a complex rate; "
        "expected a nonnegative flow",
        name=name,
        flow_rate=flow_rate,
    )
    return rate


def api_erosional_velocity(rho_fluid: float) -> float:
    """Evaluate the API erosional velocity limit.

    Parameters
    ----------
    rho_fluid : float
        Positive mixture density [kg/m3].

    Returns
    -------
    float
        Maximum flow velocity [m/s].

    Notes
    -----
    Reference: API RP 14E; GEMINI uses C=125 with historical imperial conversions.
    """
    ops.check(
        rho_fluid > 0,
        PhysicsRangeError,
        "api_erosional_velocity: rho_fluid = {rho_fluid} kg/m3; expected a positive density",
        rho_fluid=rho_fluid,
    )
    return units.API_VELOCITY_FACTOR * _API_C_FACTOR / ops.sqrt(rho_fluid)


def api_velocity_comparison(actual: float, limit: float) -> dict:
    """Compare actual and limiting flow velocities.

    Parameters
    ----------
    actual, limit : float
        Actual speed and positive limiting speed [m/s].

    Returns
    -------
    dict
        Velocity ratio [-], margin [m/s], and exceedance flag [-].

    Notes
    -----
    Reference: GEMINI WIMS API velocity comparison; margin = limit - actual.
    """
    ops.check(
        limit > 0,
        PhysicsRangeError,
        "api_velocity_comparison: limit = {limit} m/s; expected a positive velocity limit",
        limit=limit,
    )
    return {
        "velocity_ratio": actual / limit,
        "velocity_margin_ms": limit - actual,
        "exceeds_api_limit": actual > limit,
    }
