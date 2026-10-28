"""Pipe hydraulics: Swamee–Jain (1976) and Beggs–Brill (Shoham p.59)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from . import fluid as fluid_models
from . import geometry, heat_transfer, units

if TYPE_CHECKING:
    from gemini.core.types.flows import Stream
from .constants import G_FT, G


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
        Pipe angle above horizontal [rad].
    diameter, roughness, length : float
        Internal diameter, absolute roughness and interval length [m].

    Returns
    -------
    tuple of float
        Signed friction drop and gravity drop [Pa].

    Notes
    -----
    Reference: Swamee and Jain (1976), Explicit Equations for Pipe-Flow Problems,
    combined with Darcy–Weisbach and hydrostatic balance; retained GEMINI formulation.
    """
    g = G  # acceleration due to gravity (m/s2)

    if velocity == 0:
        return 0.0, rho * g * length * math.sin(inclination)

    # friction
    Rem = abs(velocity) * rho * diameter / mu
    fric_coeff = 0.25 / (
        (math.log10((roughness / (3.7 * diameter)) + (5.74 / (Rem ** (0.9))))) ** (2)
    )

    # gravity
    dp_grav = rho * g * length * math.sin(inclination)

    # friction
    dp_fric = fric_coeff * rho * length / diameter * (abs(velocity) * velocity) / 2
    return dp_fric, dp_grav


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
        Gas and liquid superficial velocities [m/s].
    rho_g, rho_l : float
        Phase densities [kg/m3].
    inclination : float
        Angle above horizontal [rad].
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
    original GEMINI implementation cites Shoham, p. 59. US-basis intermediates are
    converted at this function boundary.
    """
    us_g = units.m_to_ft(us_g)  # m/s -> ft/s
    us_l = units.m_to_ft(us_l)  # m/s -> ft/s
    rho_g = units.kgm3_to_lbmft3(rho_g)  # kg/m3 -> lbm/ft3
    rho_l = units.kgm3_to_lbmft3(rho_l)  # kg/m3 -> lbm/ft3
    mu_g = units.pas_to_cp(mu_g)  # Pa s -> cp
    mu_l = units.pas_to_cp(mu_l)  # Pa s -> cp
    sigma = units.nm_to_dyne_cm(sigma)  # N/m -> dyne/cm
    diameter = units.m_to_ft(diameter)  # m -> ft
    roughness = units.m_to_ft(roughness)  # m -> ft
    length = units.m_to_ft(length)  # m -> ft
    g = G_FT  # 32.2 lbm ft/lbf sec**2

    # preprocessing input parameters
    um = us_l + us_g
    Nlv = 1.938 * us_l * (rho_l / sigma) ** 0.25
    Ll = us_l / um

    Frm2 = um**2 / (g * diameter)

    L1 = 316 * Ll**0.302
    L2 = 0.0009252 * Ll**-2.4684
    L3 = 0.10 * Ll**-1.4516
    L4 = 0.5 * Ll**-6.738

    # reg 1 = segregated
    # reg 2 = intermittend
    # reg 3 = distributed
    # reg 4 = transition
    if (Ll < 0.01) and (Frm2 < L1):
        reg = 1

    elif (Ll >= 0.01) and (Frm2 < L2):
        reg = 1

    elif (Ll >= 0.01) and ((Frm2 >= L2) and (Frm2 <= L3)):
        reg = 4

    elif ((Ll > 0.01) and (Ll < 0.4)) and ((Frm2 >= L3) and (Frm2 <= L1)):
        reg = 2

    elif (Ll > 0.4) and ((Frm2 >= L3) and (Frm2 <= L4)):
        reg = 2

    elif (Ll < 0.4) and (Frm2 >= L1):
        reg = 3

    elif (Ll > 0.4) and (Frm2 >= L4):
        reg = 3

    else:
        reg = 0

    Hl0_1 = 0.98 * (Ll**0.4846) / (Frm2**0.0868)
    Hl0_2 = 0.845 * (Ll**0.5351) / (Frm2**0.0173)
    Hl0_3 = 1.065 * (Ll**0.5824) / (Frm2**0.0609)

    if inclination < 0:
        d = 4.7
        e = -0.3692
        f = 0.1244
        h = -0.5056
        C = max(0, (1 - Ll) * math.log(d * (Ll**e) * (Nlv**f) * (Frm2**h)))
        psi = 1 + C * (math.sin(1.8 * inclination) - 0.333 * (math.sin(1.8 * inclination)) ** 3)
        Hl_down_1 = Hl0_1 * psi
        Hl_down_2 = Hl0_2 * psi

    elif (inclination >= 0) and (reg == 1):  # segregated uphill
        d = 0.011
        e = -3.768
        f = 3.539
        h = -1.614
        C = max(0, (1 - Ll) * math.log(d * (Ll**e) * (Nlv**f) * (Frm2**h)))
        psi = 1 + C * (math.sin(1.8 * inclination) - 0.333 * (math.sin(1.8 * inclination)) ** 3)
        Hl_up_1 = Hl0_1 * psi
    elif (inclination >= 0) and (reg == 2):  # intermittend uphill
        d = 2.96
        e = 0.305
        f = -0.4473
        h = 0.0978
        C = max(0, (1 - Ll) * math.log(d * (Ll**e) * (Nlv**f) * (Frm2**h)))
        psi = 1 + C * (math.sin(1.8 * inclination) - 0.333 * (math.sin(1.8 * inclination)) ** 3)
        Hl_up_2 = Hl0_2 * psi
    elif (inclination >= 0) and (reg == 3):  # distributed uphill
        C = 0
        psi = 1
    else:  # transition uphill
        d = 0.011
        e = -3.768
        f = 3.539
        h = -1.614
        C = max(0, (1 - Ll) * math.log(d * (Ll**e) * (Nlv**f) * (Frm2**h)))
        psi = 1 + C * (math.sin(1.8 * inclination) - 0.333 * (math.sin(1.8 * inclination)) ** 3)
        Hl_up_1 = Hl0_1 * psi
        d = 2.96
        e = 0.305
        f = -0.4473
        h = 0.0978
        C = max(0, (1 - Ll) * math.log(d * (Ll**e) * (Nlv**f) * (Frm2**h)))
        psi = 1 + C * (math.sin(1.8 * inclination) - 0.333 * (math.sin(1.8 * inclination)) ** 3)
        Hl_up_2 = Hl0_2 * psi

    if reg == 0:
        Hl = 0
    elif reg == 1:
        Hl = Hl0_1 * psi
    elif reg == 2:
        Hl = Hl0_2 * psi
    elif reg == 3:
        Hl = Hl0_3 * psi
    elif reg == 4:
        A = (L3 - Frm2) / (L3 - L2)
        if inclination < 0:
            Hl = A * Hl_down_1 + (1 - A) * Hl_down_2
        else:
            Hl = A * Hl_up_1 + (1 - A) * Hl_up_2

    Hl = min(Hl, 1)
    Hl = max(Hl, 0)

    y = Ll / Hl**2
    if (y > 1) and (y < 1.2):
        s = math.log(2.2 * y - 1.2)
    else:
        s = math.log(y) / (
            -0.0523
            + 3.182 * math.log(y)
            - 0.8725 * (math.log(y)) ** 2
            + 0.01853 * (math.log(y)) ** 4
        )

    ftpfn = math.exp(s)

    if Ll == 0:
        ftpfn = 1

    # Conversion output parameter
    us_g = units.ft_to_m(us_g)  # m/s <- ft/s
    us_l = units.ft_to_m(us_l)  # m/s <- ft/s
    rho_g = units.lbmft3_to_kgm3(rho_g)  # kg/m3 <- lbm/ft3
    rho_l = units.lbmft3_to_kgm3(rho_l)  # kg/m3 <- lbm/ft3
    mu_g = units.cp_to_pas(mu_g)  # Pa s <- cp
    mu_l = units.cp_to_pas(mu_l)  # Pa s <- cp
    sigma = units.dyne_cm_to_nm(sigma)  # N/m <- dyne/cm
    diameter = units.ft_to_m(diameter)  # m <- ft
    roughness = units.ft_to_m(roughness)  # m <- ft
    length = units.ft_to_m(length)  # m <- ft
    g = G  # 32.2 lbm ft/lbf sec**2
    um = us_g + us_l

    # friction
    Ll = us_l / um
    rhom = (Ll * rho_l) + (1 - Ll) * rho_g
    etam = (Ll * mu_l) + (1 - Ll) * mu_g
    Rem = um * rhom * diameter / etam
    lambdam = (
        -0.8685 * math.log((1.964 * math.log(Rem) - 3.8215) / Rem + roughness / (diameter * 3.71))
    ) ** (-2)
    dp_fric = (0.5 * rhom * um * abs(um)) * lambdam * ftpfn * length / diameter

    # gravity
    rhom = (Hl * rho_l) + (1 - Hl) * rho_g
    dp_grav = rhom * g * length * math.sin(inclination)

    return dp_fric, dp_grav


@dataclass(frozen=True)
class PathResult:
    """Uncorrected path result: pressures [Pa], temperatures [K]."""

    p_out: float
    T_out: float
    dp_fric: float
    dp_grav: float
    section_p: list[float]
    section_T: list[float]


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
    fluid: fluid_models.ConstantWater,
    direction: Literal["up", "down"],
    u_value: float,
    t_ambient: float,
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
    fluid : ConstantWater
        Property model with properties(p, T).
    direction : str
        Traversal direction, 'up' or 'down'; flow sign is independent.
    u_value, t_ambient : float
        Heat transfer coefficient [W/m2/K] and ambient temperature [K].
    correlation, correlation_2p : str
        Single-phase and two-phase correlation names.

    Returns
    -------
    PathResult
        Uncorrected pressure [Pa], temperature [K], drops [Pa], and traversed profiles.
    """
    direction = direction.strip().lower()
    if direction not in {"up", "down"}:
        raise ValueError(f"Unsupported direction {direction!r}")
    if correlation != "darcy_weisbach" or correlation_2p != "BeggsBrill":
        raise ValueError(f"Unknown correlations {correlation!r}, {correlation_2p!r}")
    p, T = stream.p, stream.T
    initial = fluid.properties(p, T)
    flow = stream.m_dot / initial.density
    sections = path.sections if direction == "down" else reversed(path.sections)
    pressures, temperatures = [], []
    dp_friction = dp_gravity = 0.0
    for section in sections:
        if flow == 0:
            # NOTE(refactor): DPDT's zero-flow branch suppresses gravity as well as friction.
            friction = gravity = delta_T = 0.0
        else:
            f = fluid.properties(p, T)
            mass = flow * f.density
            m_l, m_g = (1 - f.gmf) * mass, f.gmf * mass
            area = math.pi / 4 * section.inner_diameter**2
            us_l = m_l / f.rho_l / area
            # NOTE(refactor): preserve gmf/rho_g/area; the old formula does not use m_g.
            us_g = f.gmf / f.rho_g / area
            if m_g == 0:
                friction, gravity = darcy_weisbach_dp(
                    us_l,
                    f.rho_l,
                    section.inclination,
                    f.mu_l,
                    section.inner_diameter,
                    section.roughness,
                    section.length,
                )
            else:
                friction, gravity = beggs_brill_dp(
                    us_g,
                    us_l,
                    f.rho_g,
                    f.rho_l,
                    section.inclination,
                    f.mu_g,
                    f.mu_l,
                    f.sigma,
                    section.inner_diameter,
                    section.roughness,
                    section.length,
                )
            delta_T = heat_transfer.pipe_temperature_change(
                T,
                u_value,
                math.pi * section.inner_diameter * section.length,
                m_l,
                m_g,
                f.cp_l,
                f.cp_g,
                t_ambient,
            )
        if direction == "down":
            p, T = max(0.001, p + friction + gravity), T + delta_T
        else:
            p, T = max(0.001, p - friction - gravity), T - delta_T
        pressures.append(p)
        temperatures.append(T)
        dp_friction += friction
        dp_gravity += gravity
    return PathResult(p, T, dp_friction, dp_gravity, pressures, temperatures)


def radial_pressure_drops(
    flow: float,
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
    flow, viscosity : float
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
    if min(permeability, thickness, drainage_radius, wellbore_radius) <= 0:
        raise ValueError("Radial-flow permeability, thickness and radii must be positive")
    denominator = 2 * math.pi * permeability * thickness
    return (
        flow * viscosity * math.log(drainage_radius / wellbore_radius) / denominator,
        flow * viscosity * skin / denominator,
    )


def corrosion_profile(
    path: geometry.PipePath,
    stream: Stream,
    fluid: fluid_models.ConstantWater,
    direction: Literal["up", "down"],
    u_value: float,
    t_ambient: float,
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
    fluid : ConstantWater
        SI property model.
    direction : str
        Traversal direction, up or down [-].
    u_value, t_ambient : float
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
    from . import corrosion

    result = pipe_path_profile(path, stream, fluid, direction, u_value, t_ambient)
    sections = path.sections if direction == "down" else list(reversed(path.sections))
    rates = []
    for section, p, T in zip(sections, result.section_p, result.section_T):
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


def erosion_check(
    path: geometry.PipePath, stream: Stream, fluid: fluid_models.ConstantWater
) -> dict:
    """Compare section velocities with the API erosional velocity limit.

    Parameters
    ----------
    path : PipePath
        Surface-to-bottom pipe intervals [m, rad].
    stream : Stream
        Mass flow [kg/s], pressure [Pa] and temperature [K].
    fluid : ConstantWater
        SI property model.

    Returns
    -------
    dict
        Section velocities and limit [m/s], dimensionless ratios and alarm flags.

    Notes
    -----
    Reference: API RP 14E velocity criterion, as implemented in GEMINI WIMS.
    """
    from . import erosion

    density = fluid.properties(stream.p, stream.T).density
    limit = erosion.api_erosional_velocity(density)
    velocity = [
        abs(stream.m_dot) / density / (math.pi * s.inner_diameter**2 / 4) for s in path.sections
    ]
    return {
        "velocity": velocity,
        "limit": limit,
        "sections": [erosion.api_velocity_comparison(v, limit) for v in velocity],
        "alarm": any(v > limit for v in velocity),
    }
