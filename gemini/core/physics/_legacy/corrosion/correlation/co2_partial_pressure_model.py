"""CO2 partial pressure helper model.

This module provides :class:`CO2PartialPressureModel` to estimate the partial
pressure of CO2 in an aqueous system given gas composition and conditions.
It computes dissolved and gaseous CO2 contributions and applies Henry's law
at system temperature.
"""

import math

from gemini.core.physics._legacy.model_abstract import StaticModel


class CO2PartialPressureModel(StaticModel):
    """Calculate CO2 partial pressure from gas/liquid conditions."""

    def __init__(self):
        """Model initialization."""
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
        # get input
        gas_pressure = u["gas_pressure"]  # Gas phase pressure at sample conditions [bar]
        co2_mol_fraction = u["co2_mol_fraction"]  # mol fraction of co2 in a gas phase[-]
        gwr = u["gas_water_ratio"]  # Gas-Water Ration [sm3/sm3]
        gas_density = u["gas_density"]  # Gas phase density [kg/m3]
        gas_molecular_weight = u["gas_molecular_weight"]  # Gas (average) molar weight [g/mol]
        temperature_sample = u["temperature_sample"]  # Temperature of the sample [C]
        temperature_system = u["temperature_system"]  # Temperature of the system [C]

        # Solubility of CO2 (Caq) + CO2 (g)
        total_dissolved_co2 = self._get_CO2_solubility_in_liquid(
            co2_mol_fraction, temperature_sample, gas_pressure
        ) + self._get_CO2_solubility_in_gas(
            co2_mol_fraction, gwr, gas_density, gas_molecular_weight
        )

        self.output["CO2 Partial Pressure [bar]"] = total_dissolved_co2 / self._get_henry_const(
            temperature_system
        )

    def get_output(self):
        """Get output of the model."""
        return self.output

    def _get_henry_const(self, temperature):
        """Calculate henry constant at given temperature.

        Parameters:
        temperature (float): Temperature in Celsius.

        Returns:
        float: Henry's constant in mol/(l*bar).
        """
        temperature_kelvin = self._convert_celsius_to_kelvin(temperature)
        henry_const = 0.0385 * math.exp(
            2400 * ((1 / temperature_kelvin) - 1 / 293.15)
        )  # mol/(l*bar)
        return henry_const

    def _get_CO2_solubility_in_liquid(self, co2_mol_fraction, temperature, gas_pressure):
        """Calculate CO2 solubility in liquid.

        Parameters
        ----------
        co2_mol_fraction : float
            Molar fraction of CO2 in gas phase.
        temperature : float
            Temperature of the sample in Celsius.
        gas_pressure : float
            Gas phase pressure at sample conditions in bar.

        Returns
        -------
        float
            CO2 solubility in liquid in mol/l.
        """
        solubility = co2_mol_fraction * self._get_henry_const(temperature) * gas_pressure  # mol/l
        return solubility

    def _get_CO2_solubility_in_gas(self, co2_mol_fraction, gwr, gas_density, gas_molecular_weight):
        """Calculate CO2 solubility in gas phase.

        Parameters
        ----------
        co2_mol_fraction : float
            Molar fraction of CO2 in gas phase.
        gwr : float
            Gas-Water Ratio in sm3/sm3.
        gas_density : float
            Gas phase density in kg/m3.
        gas_molecular_weight : float
            Gas mixture (average) molar weight in g/mol.

        Returns
        -------
        float
            CO2 solubility in mixture in mol/l.
        """
        solubility = co2_mol_fraction * gwr * gas_density / gas_molecular_weight  # mol/l
        return solubility

    @staticmethod
    def _convert_celsius_to_kelvin(temperature):
        """
        Convert temperature from Celsius to Kelvin.

        Parameters:
        temperature (float): Temperature in Celsius

        Returns:
        float: Temperature in Kelvin
        """
        return temperature + 273.15
