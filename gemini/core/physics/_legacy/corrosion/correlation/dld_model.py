"""DLD CO2 corrosion correlation (de Waard, Lotz, Dugstad, 1995).

Implements the semi-empirical correlation described in
"Influence of liquid flow velocity on CO2 corrosion: A semi-emperical model"
for predicting corrosion rate as a function of CO2 fugacity, temperature,
and hydrodynamics.
https://www.osti.gov/biblio/106125
"""

import math

from gemini.core.physics._legacy.model_abstract import StaticModel


class DLD(StaticModel):
    """CO2 corrosion rate using the DLD (1995) correlation."""

    def __init__(self):
        """Initialize DLD corrosion model."""
        self.parameters = {}
        self.output = {}

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
        """Calculate output based on input u and state x."""
        self.output["corrosion_rate"] = self.get_corrosion_rate(u)

    def get_output(self):
        """Get output of the model."""
        return self.output

    def get_corrosion_rate(self, u):
        """
        Calculate the corrosion rate based on various parameters.

        Parameters:
        parameters (dict): Dictionary containing 'co2_fraction' (float),
        'pressure' (float), 'temp_c' (float), and 'flowrate' (float)

        Returns:
        float: Corrosion rate in mm/year
        """
        co2_fraction = u.get("co2_fraction", None)
        co2_partial_pressure = u.get("co2_partial_pressure", None)

        pressure = u["pressure"]  # bar
        temperature_celsius = u["temperature"]  # C

        co2_fugacity = self._calculate_co2_fugacity(
            pressure=pressure,
            temperature_celsius=temperature_celsius,
            co2_fraction=co2_fraction,
            co2_partial_pressure=co2_partial_pressure,
        )

        corrosion_rate = 1 / (
            1 / self._calculate_reaction_controlled_corrosion(u)
            + 1 / self._calculate_mass_transfer_controlled_corrosion(u)
        )  # mm/year

        return corrosion_rate * self._calculate_scaling_factor(temperature_celsius, co2_fugacity)

    def _calculate_reaction_controlled_corrosion(self, u):
        """
        Calculate reaction-controlled corrosion rate.

        Parameters:
        parameters (dict): Dictionary containing 'co2_fraction' (float),
        'pressure' (float), and 'temp_c' (float)

        Returns:
        float: Reaction-controlled corrosion rate
        """
        co2_fraction = u.get("co2_fraction", None)
        co2_partial_pressure = u.get("co2_partial_pressure", None)

        pressure = u["pressure"]
        temperature_celsius = u["temperature"]

        co2_fugacity = self._calculate_co2_fugacity(
            pressure=pressure,
            temperature_celsius=temperature_celsius,
            co2_fraction=co2_fraction,
            co2_partial_pressure=co2_partial_pressure,
        )

        temperature_kelvin = self._convert_celsius_to_kelvin(temperature_celsius)

        return 10 ** (4.93 - 1119 / temperature_kelvin + 0.58 * math.log10(co2_fugacity))

    def _calculate_mass_transfer_controlled_corrosion(self, u):
        """
        Calculate mass transfer-controlled corrosion rate.

        Parameters:
        parameters (dict): Dictionary containing 'co2_fraction' (float),
        'pressure' (float), 'temp_c' (float), and 'flowrate' (float)

        Returns:
        float: Mass transfer-controlled corrosion rate
        """
        co2_fraction = u.get("co2_fraction", None)
        co2_partial_pressure = u.get("co2_partial_pressure", None)

        pressure = u["pressure"]
        temperature_celsius = u["temperature"]

        flow_rate = u["flow_rate"]
        pipe_diameter = self.parameters["diameter"]

        # Cross-sectional area of the pipe (A = π * D^2 / 4)
        cross_section_area = math.pi * (pipe_diameter**2) / 4.0

        # Flow velocity (v = Q / A)
        velocity = flow_rate / cross_section_area  # m/s

        co2_fugacity = self._calculate_co2_fugacity(
            pressure=pressure,
            temperature_celsius=temperature_celsius,
            co2_fraction=co2_fraction,
            co2_partial_pressure=co2_partial_pressure,
        )

        return 2.45 * (velocity**0.8 / pipe_diameter**0.2) * co2_fugacity

    def _calculate_co2_fugacity(
        self, pressure, temperature_celsius, co2_fraction=None, co2_partial_pressure=None
    ):
        """
        Calculate the fugacity of CO2.

        Parameters:
        -----------
        pressure : float
            Total pressure in the system [bar].
        temperature_celsius : float
            Temperature in Celsius.
        co2_fraction : float, optional
            Mole fraction of CO2 in the gas phase [-].
        co2_partial_pressure : float, optional
            Partial pressure of CO2 [bar]. If this is provided, co2_fraction is ignored.

        Returns:
        --------
        float
            Fugacity of CO2 in [bar].
        """
        # Convert temperature from Celsius to Kelvin
        temperature_kelvin = self._convert_celsius_to_kelvin(temperature_celsius)

        # Calculate fugacity coefficient
        if pressure <= 250:
            fugacity_coefficient = 10 ** (pressure * (0.0031 - 1.4 / temperature_kelvin))
        else:
            fugacity_coefficient = 10 ** (250 * (0.0031 - 1.4 / temperature_kelvin))

        # If CO2 partial pressure is not given, calculate it from the fraction and total pressure
        if co2_partial_pressure is None:
            if co2_fraction is None:
                raise ValueError("Either co2_fraction or co2_partial_pressure must be provided.")
            co2_partial_pressure = co2_fraction * pressure

        # Compute fugacity
        return fugacity_coefficient * co2_partial_pressure

    def _calculate_scaling_factor(self, temperature_celsius, co2_fugacity):
        """
        Calculate the scaling correction factor.

        Parameters:
        temperature_celsius (float): Temperature in Celsius
        co2_fugacity (float): Fugacity of CO2 in [bar]

        Returns:
        float: Scaling correction factor
        """
        temperature_kelvin = self._convert_celsius_to_kelvin(temperature_celsius)
        scaling_temperature_threshold = 2400 / (6.7 + 0.6 * math.log10(co2_fugacity))
        scaling_factor = 10 ** (2400 / temperature_kelvin - 0.44 * math.log10(co2_fugacity) - 6.7)

        return min(scaling_factor, 1) if temperature_kelvin >= scaling_temperature_threshold else 1

    @staticmethod
    def _convert_celsius_to_kelvin(temperature_celsius):
        """
        Convert temperature from Celsius to Kelvin.

        Parameters:
        temperature_celsius (float): Temperature in Celsius

        Returns:
        float: Temperature in Kelvin
        """
        return temperature_celsius + 273.15
