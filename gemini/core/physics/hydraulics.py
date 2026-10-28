"""Pipe hydraulics: Swamee–Jain (1976) and Beggs–Brill (Shoham p.59)."""

import math
from dataclasses import dataclass
from typing import Literal

from . import heat_transfer, units
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
    """Return friction and gravity drops [Pa] from SI inputs; inclination [rad]."""
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
    """Return friction and gravity drops [Pa] from SI inputs; inclination [rad]."""
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
    """Return hydrostatic pressure [Pa] for density [kg/m3] and height [m], rho*g*h."""
    return rho * G * height


def pipe_path_profile(
    path,
    stream,
    fluid,
    direction: Literal["up", "down"],
    u_value: float,
    t_ambient: float,
    correlation: str = "darcy_weisbach",
    correlation_2p: str = "BeggsBrill",
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
