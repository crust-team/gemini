"""Well pressure and temperature profile model.

Computes pressure drop due to friction and gravity along a multi-section well
for single- and two-phase flow, and temperature change due to heat transfer.
"""

import numpy as np

from gemini.core.physics._legacy.model_abstract import StaticModel
from gemini.core.physics._legacy.well.correlation.beggsbrill import BeggsBrill
from gemini.core.physics._legacy.well.correlation.darcyweisbach import DarcyWeisbach
from gemini.core.physics._legacy.well.correlation.temperaturedrop import TemperatureDrop


class DPDT(StaticModel):
    """Pressure and temperature along-well calculator (single/two-phase)."""

    def __init__(self):
        """Initialize well pressure drop model."""
        self.parameters = {}
        self.output = {}
        self.PVT = None

    def update_parameters(self, parameters):
        """Update model parameters.

        Parameters
        ----------
        parameters: dict
            Parameters dict as defined by the model.
        """
        for key, value in parameters.items():
            self.parameters[key] = value

    def initialize_state(self, x):
        """Generate an initial state based on user parameters."""
        pass

    def update_state(self, u, x):
        """Update the state based on input u and state x."""
        pass

    def calculate_output(self, u, x):
        """Calculate output based on input u and state x.

        The outputs are pressure drop due to friction and gravity, also the final
        pressure and temperature.
        """
        # preparing input
        Ngrid = len(self.parameters["length"])  # Number of grid cells (-)
        theta_rad = self.parameters["angle"]  # Inclinations of cells (rad)
        Lcel = self.parameters["length"]  # Length of 1 cell (m)
        Dtube = self.parameters["diameter"]  # diameter of cells (m)
        Atube = np.pi / 4 * Dtube**2  # area of cells (m2)
        Krough = self.parameters["roughness"]  # roughness of cells (mm)
        SAtube = np.pi * Dtube * Lcel  # surface area of cell (m2)
        Uvalue = 10 * np.ones(Ngrid)  # Heat transfer coefficient (W/m2.K)
        correlation = self.parameters["friction_correlation"]
        correlation_2p = self.parameters["friction_correlation_2p"]
        correction_factors = self.parameters["correction_factors"]

        direction = str(u["direction"]).strip().lower()  # down for injection and up for production
        pressure = u["pressure"]  # Pa
        temperature = u["temperature"]  # K
        flowRate = u["flowrate"]  # m3/s
        T_ambient = u["temperature_ambient"]  # K

        section_pressure = []
        section_temperature = []

        if direction == "down":
            krange = range(1, Ngrid + 1)
        elif direction == "up":
            krange = range(Ngrid, 0, -1)
        else:
            raise ValueError(f"Unsupported direction '{u['direction']}'. Use 'down' or 'up'.")

        pressuredrop_fric = 0
        pressuredrop_grav = 0

        for k in krange:

            if flowRate == 0:
                dp_fric = 0
                dp_grav = 0
                dT = 0
            else:
                rho_g, rho_l, gmf, eta_g, eta_l, cp_g, cp_l, K_g, K_l, sigma = self.PVT.get_pvt(
                    pressure, temperature
                )
                # gmf = 0.1

                # gmf is gas/liquid mass ratio, rho is density (kg/m3) and eta is viscosity (Pa.s)
                rho_mix = 1 / (gmf / rho_g + (1 - gmf) / rho_l)
                m_tot = flowRate * rho_mix
                ml = (1 - gmf) * m_tot  # kg/s
                mg = gmf * m_tot  # kg/s

                if mg == 0:
                    model = 1  # mg = 0, using darcy-weisbach model
                else:
                    model = 2  # using  beggsbrill model

                us_l = ml / rho_l / Atube[k - 1]  # superficial liquid velocity [m/s]
                us_g = gmf / rho_g / Atube[k - 1]  # superficial gas velocity [m/s]

                if model == 1:

                    if correlation == "darcy_weisbach":

                        dp_fric, dp_grav = DarcyWeisbach.calculate_dp(
                            us_l,
                            rho_l,
                            theta_rad[k - 1],
                            eta_l,
                            Dtube[k - 1],
                            Krough[k - 1],
                            Lcel[k - 1],
                        )
                    else:
                        print("The model is not implemented.")

                elif model == 2:
                    if correlation_2p == "BeggsBrill":

                        dp_fric, dp_grav = BeggsBrill.calculate_dp(
                            us_g,
                            us_l,
                            rho_g,
                            rho_l,
                            theta_rad[k - 1],
                            eta_g,
                            eta_l,
                            sigma,
                            Dtube[k - 1],
                            Krough[k - 1],
                            Lcel[k - 1],
                        )
                    else:
                        print("The model is not implemented.")
                        dp_fric = 0
                        dp_grav = 0

                else:
                    dp_fric = 0
                    dp_grav = 0

                dT = TemperatureDrop.calculate_dt(
                    temperature, Uvalue[k - 1], ml, mg, cp_l, cp_g, SAtube[k - 1], T_ambient
                )

            if direction == "down":
                pressure = max(0.001, pressure + dp_fric + dp_grav)
                temperature = temperature + dT
            elif direction == "up":
                pressure = max(0.001, pressure - dp_fric - dp_grav)
                temperature = temperature - dT

            section_pressure.append(pressure)
            section_temperature.append(temperature)

            pressuredrop_fric = pressuredrop_fric + dp_fric
            pressuredrop_grav = pressuredrop_grav + dp_grav

        self.output["pressure_output"] = correction_factors[0] * pressure + correction_factors[1]
        # Pa
        self.output["temperature_output"] = temperature  # K
        self.output["pressuredrop_fric_output"] = pressuredrop_fric  # Pa
        self.output["pressuredrop_grav_output"] = pressuredrop_grav  # Pa

        self.output["section_pressure_output"] = section_pressure  # Pa
        self.output["section_temperature_output"] = section_temperature  # K

    def get_output(self):
        """Get output of the model."""
        return self.output
