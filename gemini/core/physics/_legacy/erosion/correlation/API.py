"""API RP 14E erosion velocity limit correlation."""

import math


class ErosionAPI:
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
        C_unit = 0.3048 / math.sqrt(0.0283 / 0.454)

        U_erosion = C_unit * C / math.sqrt(rho_fluid)  # VELOCITY LIMIT FOR EROSION, m/s

        return U_erosion
