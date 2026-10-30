"""Pipe hydraulics: Darcy–Weisbach with Swamee–Jain, Beggs–Brill, path marching, radial inflow.

Inclinations are measured from horizontal [rad], positive when descending in surface-to-bottom
order, as built by :func:`geometry.build_path`. This module also composes the path marcher
with the corrosion and erosion correlations for the wells.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from gemini import ops
from gemini.errors import PhysicsRangeError, UnknownCorrelationError

from . import corrosion, erosion, geometry, heat_transfer, units
from .constants import G_FT, MIN_PATH_PRESSURE, G

if TYPE_CHECKING:
    from gemini.core.types.flows import Stream
    from gemini.core.types.fluid import Fluid

_HORIZONTAL_HOLDUP = {
    "segregated": (0.98, 0.4846, 0.0868),
    "intermittent": (0.845, 0.5351, 0.0173),
    "distributed": (1.065, 0.5824, 0.0609),
}
"""Beggs–Brill horizontal holdup ``a * lambda**b / Fr**c`` per flow regime."""

_SEGREGATED, _TRANSITION, _INTERMITTENT, _DISTRIBUTED, _OUTSIDE_MAP = 0, 1, 2, 3, -1
"""Codes of the Beggs–Brill flow regimes, and of a pair outside the regime map."""

_DOWNHILL = (4.7, -0.3692, 0.1244, -0.5056)
_SEGREGATED_UPHILL = (0.011, -3.768, 3.539, -1.614)
_INTERMITTENT_UPHILL = (2.96, 0.305, -0.4473, 0.0978)


def darcy_weisbach_dp(
    velocity: float,
    rho: float,
    inclination: float,
    mu: float,
    diameter: float,
    roughness: float,
    length: float,
) -> tuple[float, float]:
    """Evaluate signed friction and gravity pressure drops.

    Parameters
    ----------
    velocity, rho, mu : float
        Signed velocity [m/s], density [kg/m3], dynamic viscosity [Pa s].
    inclination : float
        Pipe angle from horizontal [rad], positive when descending in surface-to-bottom order.
    diameter, roughness, length : float
        Internal diameter, absolute roughness and interval length [m].

    Returns
    -------
    tuple of float
        Signed friction drop and gravity drop [Pa]; zero velocity gives zero friction.

    Notes
    -----
    Reference: Swamee and Jain (1976), Explicit Equations for Pipe-Flow Problems,
    combined with Darcy–Weisbach and hydrostatic balance; retained GEMINI formulation.
    """
    reynolds = ops.abs(velocity) * rho * diameter / mu
    friction_factor = 0.25 / (
        (ops.log10((roughness / (3.7 * diameter)) + ops.truediv(5.74, ops.pow(reynolds, 0.9))))
        ** (2)
    )
    gravity = rho * G * length * ops.sin(inclination)
    friction = friction_factor * rho * length / diameter * (ops.abs(velocity) * velocity) / 2
    return ops.where(velocity == 0, 0.0, friction), gravity


def beggs_brill_dp(
    us_g: float,
    us_l: float,
    rho_g: float,
    rho_l: float,
    inclination: float,
    mu_g: float,
    mu_l: float,
    sigma: float,
    diameter: float,
    roughness: float,
    length: float,
) -> tuple[float, float]:
    """Evaluate two-phase friction and gravity pressure drops.

    Parameters
    ----------
    us_g, us_l : float
        Gas and liquid superficial velocities [m/s]; the liquid velocity must be nonzero.
    rho_g, rho_l : float
        Phase densities [kg/m3].
    inclination : float
        Pipe angle from horizontal [rad], positive when descending in surface-to-bottom order.
    mu_g, mu_l : float
        Phase dynamic viscosities [Pa s].
    sigma : float
        Gas/liquid surface tension [N/m].
    diameter, roughness, length : float
        Pipe internal diameter, absolute roughness and interval length [m].

    Returns
    -------
    tuple of float
        Friction and gravity pressure drops [Pa].

    Notes
    -----
    Reference: Beggs and Brill (1973), A Study of Two-Phase Flow in Inclined Pipes;
    original GEMINI implementation cites Shoham, p. 59. The flow regime and holdup use the
    correlation's US basis (ft/s, lbm/ft3, dyne/cm, ft). The SI friction and gravity terms
    then use the inputs converted back from that basis, not the inputs themselves: the
    m→ft→m, kg/m3→lbm/ft3→kg/m3 and Pa·s→cP→Pa·s round trips change the last bits, and the
    goldens were captured with them.
    """
    gas_velocity, liquid_velocity = units.m_to_ft(us_g), units.m_to_ft(us_l)
    diameter_ft = units.m_to_ft(diameter)
    us_g, us_l = units.ft_to_m(gas_velocity), units.ft_to_m(liquid_velocity)
    ops.check(
        ops.logical_and(liquid_velocity != 0, liquid_velocity + gas_velocity != 0),
        PhysicsRangeError,
        "beggs_brill_dp: us_l = {us_l} m/s, us_g = {us_g} m/s; expected a nonzero liquid and "
        "mixture velocity (use darcy_weisbach_dp for single-phase flow)",
        us_l=us_l,
        us_g=us_g,
    )
    holdup, friction_multiplier = _holdup_and_friction_multiplier(
        gas_velocity,
        liquid_velocity,
        units.kgm3_to_lbmft3(rho_l),
        units.nm_to_dyne_cm(sigma),
        diameter_ft,
        inclination,
    )
    rho_g, rho_l = (units.lbmft3_to_kgm3(units.kgm3_to_lbmft3(rho)) for rho in (rho_g, rho_l))
    mu_g, mu_l = (units.cp_to_pas(units.pas_to_cp(mu)) for mu in (mu_g, mu_l))
    diameter = units.ft_to_m(diameter_ft)
    roughness, length = (units.ft_to_m(units.m_to_ft(value)) for value in (roughness, length))

    friction = _no_slip_friction((us_g, us_l), (rho_g, rho_l), (mu_g, mu_l), diameter, roughness)
    friction = friction * friction_multiplier * length / diameter
    slip_density = (holdup * rho_l) + (1 - holdup) * rho_g
    gravity = slip_density * G * length * ops.sin(inclination)
    return friction, gravity


def _no_slip_friction(velocities, densities, viscosities, diameter, roughness):
    """Return ``0.5 rho_m u_m |u_m| f_n`` [Pa/-] of the no-slip mixture.

    ``velocities``, ``densities`` and ``viscosities`` are gas and liquid pairs. The caller
    multiplies by the two-phase multiplier and ``L / D`` in the published order.
    """
    us_g, us_l = velocities
    rho_g, rho_l = densities
    mu_g, mu_l = viscosities
    mixture_velocity = us_g + us_l
    no_slip_holdup = us_l / mixture_velocity
    density = (no_slip_holdup * rho_l) + (1 - no_slip_holdup) * rho_g
    viscosity = (no_slip_holdup * mu_l) + (1 - no_slip_holdup) * mu_g
    reynolds = mixture_velocity * density * diameter / viscosity
    friction_factor = ops.pow(
        -0.8685
        * ops.log((1.964 * ops.log(reynolds) - 3.8215) / reynolds + roughness / (diameter * 3.71)),
        -2,
    )
    return (0.5 * density * mixture_velocity * ops.abs(mixture_velocity)) * friction_factor


def _holdup_and_friction_multiplier(
    gas_velocity, liquid_velocity, liquid_density, surface_tension, diameter, inclination
):
    """Return the Beggs–Brill liquid holdup [-] and two-phase friction multiplier [-].

    Inputs are on the US basis: velocities [ft/s], liquid density [lbm/ft3], surface tension
    [dyne/cm] and diameter [ft], with a nonzero liquid and mixture velocity. The holdup is
    clamped to [0, 1]; a holdup clamped to zero, which a steep downhill inclination factor can
    produce, has no friction multiplier.
    """
    mixture_velocity = liquid_velocity + gas_velocity
    liquid_velocity_number = 1.938 * liquid_velocity * (liquid_density / surface_tension) ** 0.25
    no_slip_holdup = liquid_velocity / mixture_velocity
    froude = mixture_velocity**2 / (G_FT * diameter)
    holdup = _liquid_holdup(no_slip_holdup, liquid_velocity_number, froude, inclination)
    holdup = ops.minimum(holdup, 1)
    holdup = ops.maximum(holdup, 0)
    ops.check(
        holdup != 0,
        PhysicsRangeError,
        "beggs_brill_dp: liquid holdup = 0 at inclination = {inclination} rad; expected a "
        "positive holdup (the downhill inclination factor removed all liquid)",
        holdup=holdup,
        inclination=inclination,
    )
    return holdup, _friction_multiplier(no_slip_holdup, holdup)


def _flow_regime(no_slip_holdup, froude):
    """Return the Beggs–Brill flow regime code and its L2 and L3 transition boundaries.

    The regime map follows Beggs and Brill (1973) as revised by Brill and Beggs: segregated
    for lambda < 0.01 and Fr < L1 or lambda >= 0.01 and Fr < L2; transition for
    lambda >= 0.01 and L2 <= Fr <= L3; intermittent for 0.01 <= lambda < 0.4 and
    L3 < Fr <= L1 or lambda >= 0.4 and L3 < Fr <= L4; distributed for lambda < 0.4 and
    Fr >= L1 or lambda >= 0.4 and Fr > L4. A no-slip holdup of exactly 0.4 therefore takes
    the upper range; it formerly matched no regime and divided by zero.

    The regime is one of ``_SEGREGATED``, ``_TRANSITION``, ``_INTERMITTENT`` and
    ``_DISTRIBUTED``, chosen by nested ``where`` in the order of the map; a pair outside the
    map raises.
    """
    l1 = 316 * ops.pow(no_slip_holdup, 0.302)
    l2 = 0.0009252 * ops.pow(no_slip_holdup, -2.4684)
    l3 = 0.10 * ops.pow(no_slip_holdup, -1.4516)
    l4 = 0.5 * ops.pow(no_slip_holdup, -6.738)
    low, high = no_slip_holdup < 0.01, no_slip_holdup >= 0.01
    below, above = no_slip_holdup < 0.4, no_slip_holdup >= 0.4
    segregated = ops.logical_or(
        ops.logical_and(low, froude < l1), ops.logical_and(high, froude < l2)
    )
    transition = ops.logical_and(high, ops.logical_and(l2 <= froude, froude <= l3))
    intermittent = ops.logical_or(
        ops.logical_and(ops.logical_and(high, below), ops.logical_and(l3 <= froude, froude <= l1)),
        ops.logical_and(above, ops.logical_and(l3 <= froude, froude <= l4)),
    )
    distributed = ops.logical_or(
        ops.logical_and(below, froude >= l1), ops.logical_and(above, froude >= l4)
    )
    regime = ops.where(
        segregated,
        _SEGREGATED,
        ops.where(
            transition,
            _TRANSITION,
            ops.where(
                intermittent,
                _INTERMITTENT,
                ops.where(distributed, _DISTRIBUTED, _OUTSIDE_MAP),
            ),
        ),
    )
    ops.check(
        regime != _OUTSIDE_MAP,
        PhysicsRangeError,
        "beggs_brill_dp: no-slip holdup = {no_slip_holdup}, Froude number = {froude}; "
        "expected finite values inside the flow-regime map",
        no_slip_holdup=no_slip_holdup,
        froude=froude,
    )
    return regime, l2, l3


def _liquid_holdup(no_slip_holdup, liquid_velocity_number, froude, inclination):
    """Return the inclined liquid holdup before clamping.

    Transition flow blends the segregated and intermittent holdups with the weight
    A = (L3 - Fr) / (L3 - L2). Every regime's holdup and inclination factors are evaluated and
    ``where`` selects the regime's, so the expressions equal the former per-regime branches.
    """
    regime, l2, l3 = _flow_regime(no_slip_holdup, froude)
    numbers = (no_slip_holdup, liquid_velocity_number, froude, inclination)
    segregated_holdup = _horizontal_holdup("segregated", no_slip_holdup, froude)
    intermittent_holdup = _horizontal_holdup("intermittent", no_slip_holdup, froude)
    distributed_holdup = _horizontal_holdup("distributed", no_slip_holdup, froude)
    downhill = _inclination_factor(_DOWNHILL, *numbers)
    segregated_uphill = _inclination_factor(_SEGREGATED_UPHILL, *numbers)
    intermittent_uphill = _inclination_factor(_INTERMITTENT_UPHILL, *numbers)
    is_downhill = inclination < 0

    horizontal = ops.where(
        regime == _SEGREGATED,
        segregated_holdup,
        ops.where(regime == _INTERMITTENT, intermittent_holdup, distributed_holdup),
    )
    factor = _regime_factor(
        regime, is_downhill, inclination >= 0, downhill, segregated_uphill, intermittent_uphill
    )
    weight = ops.truediv(l3 - froude, l3 - l2)
    segregated = segregated_holdup * ops.where(is_downhill, downhill, segregated_uphill)
    intermittent = intermittent_holdup * ops.where(is_downhill, downhill, intermittent_uphill)
    blended = weight * segregated + (1 - weight) * intermittent
    return ops.where(regime == _TRANSITION, blended, horizontal * factor)


def _horizontal_holdup(regime, no_slip_holdup, froude):
    """Return the horizontal-pipe holdup of one flow regime."""
    a, b, c = _HORIZONTAL_HOLDUP[regime]
    return a * (no_slip_holdup**b) / (froude**c)


def _regime_factor(
    regime, downhill, uphill, downhill_factor, segregated_factor, intermittent_factor
):
    """Return the inclination factor psi of a segregated, intermittent or distributed regime.

    Downhill flow uses the downhill coefficients in every regime and uphill distributed flow
    has psi = 1. A NaN inclination is neither downhill nor uphill and keeps the original
    fallback to the intermittent coefficients, which gives a NaN factor.
    """
    return ops.where(
        downhill,
        downhill_factor,
        ops.where(
            ops.logical_and(uphill, regime == _DISTRIBUTED),
            1,
            ops.where(
                ops.logical_and(uphill, regime == _SEGREGATED),
                segregated_factor,
                intermittent_factor,
            ),
        ),
    )


def _inclination_factor(coefficients, no_slip_holdup, liquid_velocity_number, froude, inclination):
    """Return psi = 1 + C (sin 1.8θ - 0.333 sin³ 1.8θ) with C = (1-λ) ln(d λ^e Nlv^f Fr^g)."""
    d, e, f, h = coefficients
    correction = ops.maximum(
        0,
        (1 - no_slip_holdup)
        * ops.log(d * (no_slip_holdup**e) * (liquid_velocity_number**f) * (froude**h)),
    )
    return 1 + correction * (ops.sin(1.8 * inclination) - 0.333 * (ops.sin(1.8 * inclination)) ** 3)


def _friction_multiplier(no_slip_holdup, holdup):
    """Return the two-phase friction multiplier exp(s) with y = lambda / holdup²."""
    y = no_slip_holdup / holdup**2
    log_y = ops.log(y)
    s = ops.where(
        ops.logical_and(y > 1, y < 1.2),
        ops.log(2.2 * y - 1.2),
        ops.truediv(
            log_y, -0.0523 + 3.182 * log_y - 0.8725 * (log_y) ** 2 + 0.01853 * (log_y) ** 4
        ),
    )
    return ops.exp(s)


@dataclass(frozen=True)
class PathResult:
    """Uncorrected path result: pressures [Pa], temperatures [K]."""

    p_out: float
    T_out: float
    dp_friction: float
    dp_gravity: float
    section_pressure: list[float]
    section_temperature: list[float]


def hydrostatic_dp(rho: float, height: float) -> float:
    """Evaluate hydrostatic pressure.

    Parameters
    ----------
    rho, height : float
        Density [kg/m3] and signed vertical height [m].

    Returns
    -------
    float
        Pressure difference [Pa].

    Notes
    -----
    Reference: Hydrostatic balance dp = rho*g*height; GEMINI gravity 9.81 m/s2.
    """
    return rho * G * height


def pipe_path_profile(
    path: geometry.PipePath,
    stream: Stream,
    fluid: Fluid,
    direction: Literal["up", "down"],
    u_value: float,
    ambient_temperature: float,
    correlation: Literal["darcy_weisbach"] = "darcy_weisbach",
    correlation_2p: Literal["BeggsBrill"] = "BeggsBrill",
) -> PathResult:
    """March the original DPDT equations along a pipe path using SI units.

    Parameters
    ----------
    path : PipePath
        Sections ordered from surface to bottom [m, rad].
    stream : Stream
        Inlet mass flow [kg/s], pressure [Pa] and temperature [K].
    fluid : Fluid
        Property model with properties(p, T).
    direction : str
        Traversal direction, 'up' or 'down' (case and surrounding spaces ignored); the flow
        sign is independent.
    u_value, ambient_temperature : float
        Heat transfer coefficient [W/m2/K] and ambient temperature [K].
    correlation, correlation_2p : str
        Single-phase and two-phase correlation names.

    Returns
    -------
    PathResult
        Uncorrected pressure [Pa], temperature [K], drops [Pa], and traversed profiles.

    Notes
    -----
    Marched pressures never fall below ``MIN_PATH_PRESSURE`` (0.001 Pa), so a path whose
    drops exceed the inlet pressure keeps a positive absolute pressure, as in DPDT.
    """
    direction, sections = _traversal(path, direction)
    if correlation != "darcy_weisbach" or correlation_2p != "BeggsBrill":
        raise UnknownCorrelationError(
            f"pipe_path_profile: correlation = {correlation!r}, correlation_2p = "
            f"{correlation_2p!r}; expected 'darcy_weisbach' and 'BeggsBrill'"
        )
    p, T = stream.p, stream.T
    flow = stream.m_dot / fluid.properties(p, T).density
    pressures, temperatures = [], []
    dp_friction = dp_gravity = 0.0
    for section in sections:
        friction, gravity, delta_T = _section_drops(
            section, p, T, flow, fluid, u_value, ambient_temperature
        )
        if direction == "down":
            p, T = ops.maximum(MIN_PATH_PRESSURE, p + friction + gravity), T + delta_T
        else:
            p, T = ops.maximum(MIN_PATH_PRESSURE, p - friction - gravity), T - delta_T
        pressures.append(p)
        temperatures.append(T)
        dp_friction += friction
        dp_gravity += gravity
    return PathResult(p, T, dp_friction, dp_gravity, pressures, temperatures)


def _traversal(path, direction):
    """Return the normalised direction and the path sections in traversal order."""
    direction = direction.strip().lower()
    if direction not in {"up", "down"}:
        raise UnknownCorrelationError(
            f"pipe path: direction = {direction!r}; expected 'up' or 'down'"
        )
    sections = path.sections if direction == "down" else list(reversed(path.sections))
    return direction, sections


def _section_drops(section, p, T, flow, fluid, u_value, ambient_temperature):
    """Return friction and gravity drops [Pa] and the temperature change [K] of one section.

    Two-phase reverse flow passes the liquid velocity magnitude to Beggs–Brill and reverses
    the friction sign, as Darcy–Weisbach does through ``abs(velocity) * velocity``.

    The two-phase model is chosen by ``fluid.gas_mass_fraction``, which is fixed in a trace: a
    liquid-only fluid never reaches Beggs–Brill. With free gas the gas mass flow is zero only
    at zero flow, which is the zero-flow case, so the structural test equals the former test of
    the gas mass flow. At zero flow every branch is still evaluated, so Beggs–Brill and the heat
    loss receive a harmless liquid velocity, inclination and liquid mass flow there and
    ``where`` returns the zero drops.

    NOTE(refactor): DPDT's zero-flow branch suppresses gravity as well as friction.

    NOTE(refactor): the gas superficial velocity keeps the original ``gmf / rho_g / area``,
    which does not use the gas mass flow, so two-phase regime and holdup do not follow the
    flow rate; the physical form would be ``m_g / rho_g / area``.
    """
    stopped = flow == 0
    f = fluid.properties(p, T)
    mass = flow * f.density
    m_l, m_g = (1 - f.gmf) * mass, f.gmf * mass
    area = geometry.circle_area(section.inner_diameter)
    us_l = m_l / f.rho_l / area
    us_g = f.gmf / f.rho_g / area
    shape = (section.inner_diameter, section.roughness, section.length)
    if fluid.gas_mass_fraction == 0:
        friction, gravity = darcy_weisbach_dp(us_l, f.rho_l, section.inclination, f.mu_l, *shape)
    else:
        friction, gravity = beggs_brill_dp(
            us_g,
            ops.where(stopped, 1.0, ops.abs(us_l)),
            f.rho_g,
            f.rho_l,
            ops.where(stopped, 0.0, section.inclination),
            f.mu_g,
            f.mu_l,
            f.sigma,
            *shape,
        )
        friction = ops.where(us_l < 0, -friction, friction)
    delta_T = heat_transfer.pipe_temperature_change(
        T,
        u_value,
        math.pi * section.inner_diameter * section.length,
        ops.where(stopped, 1.0, m_l),
        m_g,
        f.cp_l,
        f.cp_g,
        ambient_temperature,
    )
    return (
        ops.where(stopped, 0.0, friction),
        ops.where(stopped, 0.0, gravity),
        ops.where(stopped, 0.0, delta_T),
    )


def radial_pressure_drops(
    volume_flow: float,
    viscosity: float,
    permeability: float,
    thickness: float,
    drainage_radius: float,
    wellbore_radius: float,
    skin: float,
) -> tuple[float, float]:
    """Return radial Darcy and skin pressure drops [Pa] (Akin 2019).

    Parameters
    ----------
    volume_flow, viscosity : float
        Liquid volume flow [m3/s] and dynamic viscosity [Pa s].
    permeability, thickness, drainage_radius, wellbore_radius : float
        Permeability [m2], reservoir thickness and radii [m].
    skin : float
        Skin factor [-].

    Returns
    -------
    tuple of float
        Flow and skin pressure drops [Pa].
    """
    smallest = ops.minimum(
        ops.minimum(ops.minimum(permeability, thickness), drainage_radius), wellbore_radius
    )
    ops.check(
        ops.logical_not(smallest <= 0),
        PhysicsRangeError,
        "radial_pressure_drops: permeability = {permeability} m2, thickness = {thickness} m, "
        "drainage_radius = {drainage_radius} m, wellbore_radius = {wellbore_radius} m; "
        "expected positive values",
        permeability=permeability,
        thickness=thickness,
        drainage_radius=drainage_radius,
        wellbore_radius=wellbore_radius,
    )
    denominator = 2 * math.pi * permeability * thickness
    return (
        volume_flow * viscosity * ops.log(drainage_radius / wellbore_radius) / denominator,
        volume_flow * viscosity * skin / denominator,
    )


def corrosion_profile(
    path: geometry.PipePath,
    stream: Stream,
    fluid: Fluid,
    direction: Literal["up", "down"],
    u_value: float,
    ambient_temperature: float,
    chemistry: dict,
    model: Literal["NORSOK", "DLM", "DLD"] = "NORSOK",
) -> list[float]:
    """Evaluate section corrosion along the traversed hydraulic profile.

    Parameters
    ----------
    path : PipePath
        Surface-to-bottom intervals [m, rad].
    stream : Stream
        Signed mass flow [kg/s], inlet pressure [Pa] and temperature [K].
    fluid : Fluid
        SI property model.
    direction : str
        Traversal direction, up or down [-].
    u_value, ambient_temperature : float
        Heat transfer coefficient [W/m2/K] and ambient temperature [K].
    chemistry : dict
        Keyword arguments for co2_corrosion_rate in its documented SI units.
    model : str
        NORSOK, DLM or DLD correlation [-].

    Returns
    -------
    list of float
        Wall penetration rates [mm/year] in traversal order.

    Notes
    -----
    Reference: GEMINI WIMS composition of DPDT and CO2 corrosion correlations;
    see pipe_path_profile and corrosion.co2_corrosion_rate.
    """
    result = pipe_path_profile(path, stream, fluid, direction, u_value, ambient_temperature)
    _, sections = _traversal(path, direction)
    rates = []
    for section, p, T in zip(sections, result.section_pressure, result.section_temperature):
        f = fluid.properties(p, T)
        rates.append(
            corrosion.co2_corrosion_rate(
                model,
                temperature=T,
                pressure=p,
                water_flow_rate=abs(stream.m_dot) / f.density,
                water_density=f.rho_l,
                water_viscosity=f.mu_l,
                diameter=section.inner_diameter,
                roughness=section.roughness,
                **chemistry,
            )
        )
    return rates


def erosion_check(path: geometry.PipePath, stream: Stream, fluid: Fluid) -> dict:
    """Compare section velocities with the API erosional velocity limit.

    Parameters
    ----------
    path : PipePath
        Surface-to-bottom pipe intervals [m, rad].
    stream : Stream
        Mass flow [kg/s], pressure [Pa] and temperature [K].
    fluid : Fluid
        SI property model.

    Returns
    -------
    dict
        Section velocities and limit [m/s], dimensionless ratios and alarm flags.

    Notes
    -----
    Reference: API RP 14E velocity criterion, as implemented in GEMINI WIMS.
    """
    density = fluid.properties(stream.p, stream.T).density
    limit = erosion.api_erosional_velocity(density)
    velocity = [
        abs(stream.m_dot) / density / geometry.circle_area(s.inner_diameter) for s in path.sections
    ]
    return {
        "velocity": velocity,
        "limit": limit,
        "sections": [erosion.api_velocity_comparison(v, limit) for v in velocity],
        "alarm": any(v > limit for v in velocity),
    }
