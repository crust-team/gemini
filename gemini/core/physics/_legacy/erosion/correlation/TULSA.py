"""E/CRC Tulsa erosion correlation."""

import math

from gemini.core.physics._legacy.erosion.correlation._common import mass_flow_and_velocity


class ErosionTULSA:
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
        mp, Up, A_pipe = mass_flow_and_velocity(input["flowRate"], dens_liq, D)

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

        C_unit = 1000 * (3600 * 24 * 365.25)  # conversion m/s --> mm/yr

        ER = C * Hb_ ** (-0.59) * Fs * Up**n * F  # [kg/kg]

        #     EL = ER * mp; % [kg/s]
        #     EL = ER * mp / rho_pipe; % [m3/s]
        #     EL = ER * mp / rho_pipe / A_t; % [m/s]
        EL = C_unit * ER * mp / (rho_pipe * A_t)  # [mm/yr]

        return EL
