"""DNV RP O501 erosive wear correlation."""

import math

from gemini.core.physics._legacy.erosion.correlation._common import mass_flow_and_velocity


class ErosionDNV:
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
        mp, Up, A_pipe = mass_flow_and_velocity(input["flowRate"], dens_liq, D)

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
        C_unit = 1000 * (3600 * 24 * 365.25)  # conversion m/s --> mm/yr

        EL = C_unit * mp * K * Up**n * F / (rho_pipe * A_t)  # [mm/yr]

        return EL
