"""OKA particle-impact erosion correlation."""

import math

from gemini.core.physics._legacy.erosion.correlation._common import mass_flow_and_velocity


class ErosionOKA:
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
        mp, Up, A_pipe1 = mass_flow_and_velocity(input["flowRate"], dens_liq, D)

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

        EL = (3600 * 24 * 365.25) * mp / A_t * E_alpha  # [mm/yr]

        return EL
