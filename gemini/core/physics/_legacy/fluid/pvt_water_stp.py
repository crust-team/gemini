"""Simple water PVT properties near STP.

Provides constant representative properties for water at standard
conditions.
"""


class PVTConstantSTP:
    """Water PVT at standard conditions (constant properties)."""

    def __init__(self):
        """Initialize PVT water STP model."""
        self.parameters = {}
        self.parameters["pressure_max"] = 500e5
        self.parameters["pressure_min"] = 1e5
        self.parameters["temperature_max"] = 100 + 273.15
        self.parameters["temperature_min"] = 0 + 273.15

        self.parameters["RHOG"] = 1.976  # CO2 gas density (kg/m3)
        self.parameters["RHOL"] = 1000  # H2O Liquid density (kg/m3)
        self.parameters["GMF"] = 0  # gas mass fraction (-)
        self.parameters["VISG"] = 21.29e-6  # CO2 Gas viscosity (Pa.s)
        self.parameters["VISL"] = 1e-3  # H2O viscosity (Pa.s)
        self.parameters["CPG"] = 0.819e3  # CO2 heat capacity (J/Kg K)
        self.parameters["CPL"] = 4.2174e3  # H2O Heat capacity (J/Kg K)
        self.parameters["HG"] = 484.665  # CO2 Enthalpy (KJ/Kg)
        self.parameters["HL"] = 0.000612  # H2O Enthalpy ((KJ/Kg)
        self.parameters["TCG"] = 14.7e-3  # CO2 thermal conductivity (W/m K)
        self.parameters["TCL"] = 1.6  # H2O thermal conductivity (W/m K)
        self.parameters["SIGMA"] = 72.8e-3  # Water-CO2 surface tension (N/m)
        self.parameters["SG"] = 9381.68  # CO2 Entropy (K/Kg K)
        self.parameters["SL"] = 0  # H2O Entropy (K/Kg K)

    def update_parameters(self, parameters):
        """Update model parameters.

        Parameters
        ----------
        parameters: dict
            Parameters dict as defined by the model.
        """
        for key, value in parameters.items():
            self.parameters[key] = value

    def get_pvt(self, P, T):
        """Calculate the PVT parameters based on pressure and temperature.

        Parameters
        ----------
        P : float
            Pressure (Pa).
        T : float
            Temperature (K).

        Returns
        -------
        rho_g : float
            Gas density (kg/m3).
        rho_l : float
            Liquid density (kg/m3).
        gmf : float
            Gas mass fraction (-).
        eta_g : float
            Viscosity gas (Pa.s).
        eta_l : float
            Viscosity liquid (Pa.s).
        cp_g : float
            Heat capacity gas (J/Kg/K).
        cp_l : float
            Heat capacity liquid (J/Kg/K).
        K_g : float
            Thermal conductivity gas (W/m/K).
        K_l : float
            Thermal conductivity liquid (W/m/K).
        sigma : float
            Surface tension (N/m).
        """
        # Density of Gas, Oil & Water. rho_l is a psuedo density of liquid phase
        rho_g = self.parameters["RHOG"]  # density gas (kg/m3)
        rho_l = self.parameters["RHOL"]  # density liquid (kg/m3)

        # Gas mass fraction of gas + water
        gmf = self.parameters["GMF"]  # gas mass fraction (-)

        # Viscosity of Gas & Water
        eta_g = self.parameters["VISG"]  # viscosity gas (Pa.s)
        eta_l = self.parameters["VISL"]  # viscosity liquid (Pa.s)

        # Heat capacity of gas & liquid
        cp_g = self.parameters["CPG"]  # heat capacity gas (J/Kg/K)
        cp_l = self.parameters["CPL"]  # heat capacity liquid (J/Kg/K)

        # Thermal conductivity of gas & liquid
        K_g = self.parameters["TCG"]  # thermal conductivity gas (W/m/K)
        K_l = self.parameters["TCL"]  # thermal conductivity liquid (W/m/K)

        # Interfacial tension of Gas-Water & Gas-Oil interface
        sigma = self.parameters["SIGMA"]  # Surface tension (N/m)

        return rho_g, rho_l, gmf, eta_g, eta_l, cp_g, cp_l, K_g, K_l, sigma
