"""Simple temperature drop model using an overall heat transfer coefficient."""


class TemperatureDrop:
    """Calculate temperature change from heat loss to ambient."""

    @staticmethod
    def calculate_dt(t_in, U, ml, mg, cp_l, cp_g, Atube, t_ambient):
        """Calculate temperature change from heat loss to ambient.

        Parameters
        ----------
        t_in: float
            input pipe temperature (K)
        U: float
            heat transfer coeff (W/m2.K)
        ml: float
            liquid mass flowrate (kg/s)
        mg: float
            gas mass flowrate (kg/s)
        cp_l: float
            liquid heat capacity (J/Kg/K)
        cp_g: float
            gas heat capacity (J/Kg/K)
        Atube: float
            surface area (m2)
        t_ambient: float
            ambient temperature (K)

        Returns
        -------
        dT: float
            delta pipe temperature (K)
        """
        # get the heat flux from ambient to well
        mtot = ml + mg
        mlfrac = ml / mtot
        mgfrac = mg / mtot
        cp_mix = mlfrac * cp_l + mgfrac * cp_g

        # get the heat flux from ambient to well
        Q_dash = U * Atube * (t_in - t_ambient)

        dT = Q_dash / (mtot * cp_mix)

        return dT
