"""Erosion correlations: DNV RP O501, OKA, E/CRC Tulsa and API RP 14E."""

import math
from typing import Literal

from . import units


def _mass_flow_and_velocity(flow_rate_m3h, rho_fluid_kgm3, diameter_m):
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
    mp_kgs = flow_rate_m3h * rho_fluid_kgm3 / units.SECONDS_PER_DAY * 24

    # -- pipe cross-section + mixture velocity --------------------------
    a_pipe_m2 = 0.25 * math.pi * diameter_m**2
    up_ms = mp_kgs / (rho_fluid_kgm3 * a_pipe_m2)

    return mp_kgs, up_ms, a_pipe_m2


class _ErosionAPI:
    """Class for API erosion model."""

    @staticmethod
    def calculate_erosion_velocity(rho_fluid):
        """Calculate maximum erosion flow velocity.

        Parameters
        ----------
        rho_fluid: float
            mixture density of fluid (kg/m3)

        Returns
        --------
        U_erosion: float
            maximum erosion flow velocity (m/s)
        """
        C = 125
        C_unit = units.API_VELOCITY_FACTOR

        U_erosion = C_unit * C / math.sqrt(rho_fluid)  # VELOCITY LIMIT FOR EROSION, m/s

        return U_erosion


class _ErosionDNV:
    """Class for DNV erosion model.

    source: https://wiki.pengtools.com/images/9/91/RP_O501_EROSIVE_WEAR_IN_PIPING_SYSTEMS.pdf
    """

    @staticmethod
    def calculate_erosion_rate(input):
        """Calculate maximum erosion rate per year.

        Parameters
        ----------
        alpha: float
            particle impact angle (deg)
        mater: string
            material (steel, titanium, GRP, Vinyl Ester)
        rho_fluid: float
            mixture density of fluid (kg/m3)
        diameter: float
            inner diameter of the pipe (m)
        flowRate: float
            fluid flow rate (m3/h)

        Returns
        --------
        EL: float
            erosion rate (mm/y or mpy)
        """
        alpha = input["alpha"]
        material = input["mater"]
        if material.lower() == "steel":
            K = 2e-9
            n = 2.6
            rho_pipe = 7800
        elif material.upper() == "titanium":
            K = 2e-9
            n = 2.6
            rho_pipe = 4500
        elif material.lower() == "grp/epoxy":
            K = 0.3e-9
            n = 3.6
            rho_pipe = 1800
        elif material.lower() == "grp/vinyl ester":
            K = 0.6e-9
            n = 3.6
            rho_pipe = 1800
        else:
            raise ValueError(f"Unknown mater '{material}' for DNV erosion.")

        D = input["diameter"]
        dens_liq = input["rho_fluid"]
        # mp [kg/s], Up [m/s] (mixture velocity in multiphase), A_pipe [m2]
        mp, Up, A_pipe = _mass_flow_and_velocity(input["flowRate"], dens_liq, D)

        aa = alpha * math.pi / 180
        F = aa * (
            9.37
            + aa
            * (
                -42.295
                + aa
                * (
                    110.864
                    + aa * (-175.804 + aa * (170.137 + aa * (-98.398 + aa * (31.211 - 4.17 * aa))))
                )
            )
        )

        A_t = A_pipe / math.sin(aa)  # m2
        C_unit = 1000 * units.SECONDS_PER_YEAR  # conversion m/s --> mm/yr

        EL = C_unit * mp * K * Up**n * F / (rho_pipe * A_t)  # [mm/yr]

        return EL


class _ErosionOKA:
    """Class for OKA erosion model.

    source: https://www.sciencedirect.com/science/article/pii/S0043164805000979
    """

    @staticmethod
    def calculate_erosion_rate(input):
        """Calculate maximum erosion rate per year.

        Parameters
        ----------
        alpha: float
            particle impact angle (deg)
        material_particles: string
            material of particle (SIO2, SIC, Glass)
        diameter_particles: float
            diamater of particle (mm)
        Hv: float
            vickers  hardness (GPa)
        rho_fluid: float
            mixture density of fluid (kg/m3)
        diameter: float
            inner diameter of the pipe (m)
        flowRate: float
            fluid flow rate (m3/h
        Returns
        --------
        EL: float
            erosion rate (mm/y or mpy)
        """
        alpha = input["alpha"]
        D = input["diameter"]
        dens_liq = input["rho_fluid"]
        # mp [kg/s], Up [m/s] (mixture velocity in multiphase), A_pipe1 [m2]
        mp, Up, A_pipe1 = _mass_flow_and_velocity(input["flowRate"], dens_liq, D)

        Hv = input["Hv"]  # Vickers [GPa] NB:Hv[GPa] = 0.009807*Hv_
        material_particles = input["mater_particle"]
        dp = input["diameter_particle"]

        if material_particles.upper() == "SIO2":
            # SiO2 particles
            Upref = 104
            dpref = 326
            k1 = -0.12
            k2 = 2.3 * Hv**0.038
            k3 = 0.19
            K = 65
        elif material_particles.upper() == "SIC":
            # SiC particles
            Upref = 99
            dpref = 326
            k1 = -0.05
            k2 = 3 * Hv**0.085
            k3 = 0.19
            K = 45
        elif material_particles.upper() == "GLASS":
            # Glass beads
            Upref = 100
            dpref = 200
            k1 = -0.16
            k2 = 2.1
            k3 = 0.19
            K = 27
        else:
            raise ValueError(
                f"Unknown mater_particle '{material_particles}'. " "Use SIO2, SIC, or GLASS."
            )

        a = 1
        b = 1

        aa = alpha * math.pi / 180
        A_pipe = A_pipe1 * 1e6  # [mm2]
        A_t = A_pipe / math.sin(aa)  # [mm2]

        E_alpha = K * (a * Hv) ** (k1 * b) * (Up / Upref) ** k2 * (dp / dpref) ** k3  # [mm3/kg]

        EL = units.SECONDS_PER_YEAR * mp / A_t * E_alpha  # [mm/yr]

        return EL


class _ErosionTULSA:
    """Class for Tulsa erosion model.

    source: http://www.ecrc.utulsa.edu/
    """

    @staticmethod
    def calculate_erosion_rate(input):
        """Calculate maximum erosion rate per year.

        Parameters
        ----------
        alpha: float
            particle impact angle (deg)
        material_particles: string
            material of particle (SIO2, SIC, Glass)
        diameter_particles: float
            diamater of particle (m)
        Hv: float
            vickers  hardness (GPa)
        fs: float
            Particle shape factor (0.2-1) 0.2 fully rounded - 1 sharp edges
        rho_fluid: float
            mixture density of fluid (kg/m3)
        diameter: float
            inner diameter of the pipe (m)
        flowRate: float
            fluid flow rate (m3/h
        Returns
        --------
        EL: float
            erosion rate (mm/y or mpy)
        """
        alpha = input["alpha"]  # particle impact angle [deg]
        rho_pipe = input["rho_pipe"]  # density of pipe material
        D = input["diameter"]  # diameter of pipe [m]
        dens_liq = input["rho_fluid"]  # kg/m3
        # mp [kg/s], Up [m/s] (mixture velocity in multiphase), A_pipe [m2]
        mp, Up, A_pipe = _mass_flow_and_velocity(input["flowRate"], dens_liq, D)

        Hv = input["Hv"]  # Vickers [GPa] NB:Hv[GPa] = 0.009807*Hv_
        # Particle shape factor: 1 sharp, 0.53 semi-rounded, 0.2 fully rounded
        Fs = input["fs"]

        aa = alpha * math.pi / 180
        F = 5.4 * aa - 10.11 * aa**2 + 10.93 * aa**3 - 6.33 * aa**4 + 1.42 * aa**5

        A_t = A_pipe / math.sin(aa)  # [m2]

        Hv_ = Hv / 0.009807  # unit-less, http://www.iron-foundry.com/castings-hardness.html
        Hb_ = Hv_ * 0.95057 - 0.03743  # http://www.iron-foundry.com/castings-hardness.html
        C = 2.17e-7
        n = 2.41

        C_unit = 1000 * units.SECONDS_PER_YEAR  # conversion m/s --> mm/yr

        ER = C * Hb_ ** (-0.59) * Fs * Up**n * F  # [kg/kg]

        #     EL = ER * mp; % [kg/s]
        #     EL = ER * mp / rho_pipe; % [m3/s]
        #     EL = ER * mp / rho_pipe / A_t; % [m/s]
        EL = C_unit * ER * mp / (rho_pipe * A_t)  # [mm/yr]

        return EL


MODEL_DNVGL = "DNVGL"
MODEL_OKA = "OKA"
MODEL_API = "API"
MODEL_TULSA = "E/CRC Tulsa"

# Map user-facing spellings (upper-cased) to canonical names.
_ALIASES = {
    "DNVGL": MODEL_DNVGL,
    "DNV": MODEL_DNVGL,
    "OKA": MODEL_OKA,
    "API": MODEL_API,
    "E/CRC TULSA": MODEL_TULSA,
    "TULSA": MODEL_TULSA,
    "ECRC": MODEL_TULSA,
}

# Canonical name -> correlation class exposing calculate_erosion_rate().
_RATE_CORRELATIONS = {
    MODEL_DNVGL: _ErosionDNV,
    MODEL_OKA: _ErosionOKA,
    MODEL_TULSA: _ErosionTULSA,
}


def normalize_model_name(name):
    """Resolve a user-facing erosion model name to its canonical form."""
    key = str(name).strip().upper()
    canonical = _ALIASES.get(key)
    if canonical is None:
        raise ValueError(f"Unknown erosion_model '{name}'.")
    return canonical


def is_velocity_model(name):
    """Return whether the model yields a velocity limit (API) rather than a rate."""
    return normalize_model_name(name) == MODEL_API


def erosion_rate(
    model: Literal["DNV", "OKA", "TULSA"],
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
        DNV, OKA or TULSA, including legacy aliases.
    flow_rate, rho_fluid, diameter : float
        Volume flow [m3/s], density [kg/m3], internal diameter [m].
    alpha, material, hardness : float, str, float
        Impact angle [rad], pipe material [-], Vickers hardness [Pa].
    particle_material, particle_diameter : str, float
        Particle material [-] and diameter [m].
    rho_pipe, shape_factor : float
        Pipe density [kg/m3] and particle shape factor [-].

    Returns
    -------
    float
        Erosion rate [mm/year]. API is available separately as a velocity limit.
    """
    name = normalize_model_name(model)
    if name == MODEL_API:
        raise ValueError("API is a velocity limit; use api_erosional_velocity")
    # NOTE(refactor): particle mass flow equals total fluid mass flow; no solids fraction.
    # NOTE(refactor): OKA documents particle diameter as mm; retain it despite dpref=326.
    # NOTE(refactor): DNV's uppercase comparison to 'titanium' remains unreachable, as before.
    data = dict(
        flowRate=units.m3s_to_m3h(flow_rate),
        rho_fluid=rho_fluid,
        diameter=diameter,
        alpha=units.rad_to_deg(alpha),
        mater=material,
        Hv=units.pa_to_gpa(hardness),
        mater_particle=particle_material,
        diameter_particle=units.m_to_mm(particle_diameter),
        rho_pipe=rho_pipe,
        fs=shape_factor,
    )
    return float(_RATE_CORRELATIONS[name].calculate_erosion_rate(data))


def api_erosional_velocity(rho_fluid: float) -> float:
    """Return API RP 14E velocity limit [m/s] from mixture density [kg/m3]."""
    if rho_fluid <= 0:
        raise ValueError(f"Density must be positive, got {rho_fluid}")
    return _ErosionAPI.calculate_erosion_velocity(rho_fluid)


def api_velocity_comparison(actual: float, limit: float) -> dict:
    """Compare actual and limiting speeds [m/s], preserving WIMS margin and ratio."""
    if limit <= 0:
        raise ValueError("Velocity limit must be positive")
    return {
        "velocity_ratio": actual / limit,
        "velocity_margin_ms": limit - actual,
        "exceeds_api_limit": actual > limit,
    }
