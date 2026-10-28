"""CO2 corrosion correlations (NORSOK M-506, de Waard–Lotz 1991/1995)."""

import bisect
import math
from typing import Literal

import numpy as np

from . import units


class _DLD:
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
        return units.c_to_k(temperature_celsius)


class _DLM:
    """CO2 corrosion rate using the DLM (1991) correlation."""

    def __init__(self):
        """Initialize DLM corrosion model."""
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
        u (dict): Dictionary containing the required
        parameters for corrosion rate calculation.

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

        temperature_kelvin = self._convert_celsius_to_kelvin(temperature_celsius)

        corrosion_rate = 10 ** (
            5.8 - 1710 / temperature_kelvin + 0.67 * math.log10(co2_fugacity)
        ) * self._calculate_scaling_factor(temperature_celsius, co2_fugacity)
        return corrosion_rate

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
        float: Fugacity of CO2 in [bar]
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
        scaling_factor = 10 ** (2400 / temperature_kelvin - 0.6 * math.log10(co2_fugacity) - 6.7)

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
        return units.c_to_k(temperature_celsius)


class _NORSOK:
    """CO2 corrosion rate using the NORSOK M-506 correlation."""

    def __init__(self):
        """Initialize NORSOK corrosion model."""
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
        self.output["corrosion_rate"] = self.calculate_corrosion_rate(u)

    def get_output(self):
        """Get output of the model."""
        return self.output

    def calculate_corrosion_rate(self, u):
        """
        Calculate the corrosion rate based on various parameters.

        Parameters:
        u (dict): Dictionary containing the required
        parameters for corrosion rate calculation.

        Returns:
        float: Corrosion rate in mm/year
        """
        co2_fraction = u.get("co2_fraction", None)
        co2_partial_pressure = u.get("co2_partial_pressure", None)

        pressure = u["pressure"]
        temperature = u["temperature"]
        water_density = u["water_density"]
        water_viscosity = u["water_viscosity"]
        water_flow_rate = u["water_flow_rate"]
        pipe_roughness = self.parameters["roughness"]
        pipe_diameter = self.parameters["diameter"]
        bicarb_concentration = u["bicarb_concentration"]
        ionic_strength = u["ionic_strength"]

        co2_fugacity = self._calculate_co2_fugacity(
            pressure=pressure,
            temperature_celsius=temperature,
            co2_fraction=co2_fraction,
            co2_partial_pressure=co2_partial_pressure,
        )

        shear_stress = self._calculate_shear_stress(
            water_density, water_viscosity, pipe_diameter, pipe_roughness, water_flow_rate
        )

        if co2_partial_pressure is not None:
            co2_pressure = co2_partial_pressure
        elif co2_fraction is not None:
            co2_pressure = co2_fraction * pressure
        else:
            # If neither is provided, we can’t proceed
            raise ValueError("Either 'co2_partial_pressure' or 'co2_fraction' must be provided.")
        ph = self._calculate_ph(
            temperature, pressure, co2_pressure, bicarb_concentration, ionic_strength
        )

        ph_fixed = self._adjust_ph_for_temperature(temperature, ph)
        kt = self._interpolate_kt_value(temperature)
        shear_factor = (shear_stress / 19) ** (0.146 + 0.0324 * math.log10(co2_fugacity))
        co2_fugacity_factor = co2_fugacity**0.62
        corrosion_rate = kt * co2_fugacity_factor * shear_factor * ph_fixed
        return corrosion_rate

    def _interpolate_kt_value(self, temperature):
        """
        Calculate the interpolated Kt value for a given temperature.

        Parameters:
        temperature (float): The temperature for which the Kt value is to be calculated.

        Returns:
        float: The interpolated Kt value.
        """
        temperatures = (5, 15, 20, 40, 60, 80, 90, 120, 150)
        kt_values = (0.42, 1.59, 4.762, 8.927, 10.695, 9.949, 6.250, 7.770, 5.203)
        pos = bisect.bisect_left(temperatures, temperature)

        if pos == 0:
            return kt_values[0]
        if pos == len(temperatures):
            return kt_values[-1]

        temp_l = temperatures[pos - 1]
        temp_u = temperatures[pos]
        kt_lower = kt_values[pos - 1]
        kt_upper = kt_values[pos]

        return kt_lower + (temperature - temp_l) * (kt_upper - kt_lower) / (temp_u - temp_l)

    def _calculate_ph(
        self,
        temperature,
        pressure,
        co2_pressure,
        bicarb_concentration,
        ionic_strength,
        calc_of_ph=10,
    ):
        """
        Calculate the pH of the solution.

        Parameters:
        temperature (float): Temperature in Celsius
        pressure (float): Pressure in the system [bar]
        co2_pressure (float): CO2 partial pressure [bar]
        bicarb_concentration (float): Bicarbonate concentration [mg/l]
        ionic_strength (float): Ionic strength [g/l]
        calc_of_ph (int): Number of pH calculations to perform [-]

        Returns:
        float: Calculated pH
        """
        bicarb = bicarb_concentration / (1000 * 61.2)
        temp_fahrenheit = units.c_to_f(temperature)
        temp_kelvin = self._convert_celsius_to_kelvin(temperature)
        ionic_strength_adjusted = ionic_strength / 58.44
        pressure_psi = units.bar_to_psi(pressure)

        h0 = (14.5 / 1.00258) * 10 ** (
            -(
                2.27
                + 0.00565 * temp_fahrenheit
                - 0.00000806 * temp_fahrenheit**2
                + 0.075 * ionic_strength_adjusted
            )
        )
        k0 = 0.00258
        k1 = 387.6 * 10 ** (
            -(
                6.41
                - 0.001594 * temp_fahrenheit
                + 0.00000852 * temp_fahrenheit**2
                - 0.0000307 * pressure_psi
                - 0.4772 * ionic_strength_adjusted**0.5
                + 0.118 * ionic_strength_adjusted
            )
        )
        k2 = 10 ** (
            -(
                10.61
                - 0.00497 * temp_fahrenheit
                + 0.00001331 * temp_fahrenheit**2
                - 0.00002624 * pressure_psi
                - 1.166 * ionic_strength_adjusted**0.5
                + 0.3466 * ionic_strength_adjusted
            )
        )
        ksp_feco3 = 10 ** (-(10.13 + 0.0182 * temperature))
        kw = 10 ** (-(29.3868 - 0.0737549 * temp_kelvin + 7.47881 * 10 ** (-5) * temp_kelvin**2))

        for _ in range(calc_of_ph):
            sat_pH_coeff = (
                0 if calc_of_ph == 1 else (2 * ksp_feco3 / (h0 * k0 * k1 * k2 * co2_pressure))
            )
            iterations = 0
            h_ion = 10**-3.5 if co2_pressure <= 20 else 10**-2.9

            while True:
                f_h_ion = (
                    sat_pH_coeff * h_ion**4
                    + h_ion**3
                    + bicarb * h_ion**2
                    - h_ion * (k1 * k0 * h0 * co2_pressure + kw)
                    - 2 * k1 * k2 * k0 * h0 * co2_pressure
                )
                f_prime_h_ion = (
                    4 * sat_pH_coeff * h_ion**3
                    + 3 * h_ion**2
                    + 2 * bicarb * h_ion
                    - (k1 * k0 * h0 * co2_pressure + kw)
                )
                h_ion_next = h_ion - f_h_ion / f_prime_h_ion

                if abs(h_ion_next - h_ion) < 10**-6 * h_ion or iterations >= 100:
                    break
                h_ion = h_ion_next
                iterations += 1

            if h_ion > 0:
                ph = round(-(math.log(h_ion) / 2.3026), 2)
            else:
                ph = 99.99
        return ph

    def _calculate_co2_fugacity(
        self, pressure, temperature_celsius, co2_fraction=None, co2_partial_pressure=None
    ):
        """Calculate the fugacity of CO2.

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

    @staticmethod
    def _calculate_shear_stress(
        water_density, water_viscosity, pipe_diameter, pipe_roughness, water_flowrate
    ):
        """Calculate the shear stress in the pipeline for a multiphase flow of oil, gas, and water.

        Returns:
        float: Shear stress in the pipeline (Pa)
        """
        # Made this way for potential 3 phase flow.
        # Convert flow rates from m3/hr to m3/s
        water_flow_rate = units.m3day_to_m3s(water_flowrate)

        # Calculate superficial velocities (m/s)
        area = math.pi * (pipe_diameter / 2) ** 2  # area in m2
        v_sw = water_flow_rate / area
        v_m = v_sw

        # Calculate mixture properties
        density_mixture = (water_density * water_flow_rate) / (water_flow_rate)
        viscosity_mixture = (water_viscosity * water_flow_rate) / (water_flow_rate) / 1000
        friction_factor = 0.001375 * (
            1
            + (
                20000 * pipe_roughness / pipe_diameter
                + 10**6 * viscosity_mixture / (v_m * pipe_diameter * density_mixture)
            )
            ** 0.33
        )
        shear_stress = 0.5 * density_mixture * friction_factor * v_m**2
        return shear_stress

    @staticmethod
    def _adjust_ph_for_temperature(temperature, initial_ph):
        """
        Calculate pH fixed for temperature.

        Parameters:
        temperature (float): Temperature in Celsius
        initial_ph (float): Initial pH value

        Returns:
        float: pH value fixed for temperature
        """
        ph = 7
        if temperature == 5.0:
            if 3.5 <= initial_ph <= 4.6:
                ph = 2.0676 + 0.2309 * initial_ph
            elif 4.6 < initial_ph <= 6.5:
                ph = 4.342 - 1.061 * initial_ph + 0.0708 * initial_ph**2
        elif temperature == 15.0:
            if 3.5 <= initial_ph <= 4.6:
                ph = 2.0676 - 0.2309 * initial_ph
            elif 4.6 < initial_ph <= 6.5:
                ph = 4.986 - 1.191 * initial_ph + 0.0708 * initial_ph**2
        elif temperature == 20.0:
            if 3.5 <= initial_ph <= 4.6:
                ph = 2.0676 - 0.2309 * initial_ph
            elif 4.6 < initial_ph <= 6.5:
                ph = 5.1885 - 1.2353 * initial_ph + 0.0708 * initial_ph**2
        elif temperature == 40.0:
            if 3.5 <= initial_ph <= 4.6:
                ph = 2.0676 - 0.2309 * initial_ph
            elif 4.6 < initial_ph <= 6.5:
                ph = 5.1885 - 1.2353 * initial_ph + 0.0708 * initial_ph**2
        elif temperature == 60.0:
            if 3.5 <= initial_ph <= 4.6:
                ph = 1.836 - 0.1818 * initial_ph
            elif 4.6 < initial_ph <= 6.5:
                ph = 15.444 - 6.1291 * initial_ph + 0.8204 * initial_ph**2 - 0.0371 * initial_ph**3
        elif temperature == 80.0:
            if 3.5 <= initial_ph <= 4.6:
                ph = 2.6727 - 0.3636 * initial_ph
            elif 4.6 < initial_ph <= 6.5:
                ph = 331.68 * math.exp(-1.2618 * initial_ph)
        elif temperature == 90.0:
            if 3.5 <= initial_ph <= 4.57:
                ph = 3.1355 - 0.4673 * initial_ph
            elif 4.57 < initial_ph <= 5.62:
                ph = 21254 * math.exp(-2.1811 * initial_ph)
            elif 5.62 < initial_ph <= 6.5:
                ph = 0.4014 - 0.0538 * initial_ph
        elif temperature == 120.0:
            if 3.5 <= initial_ph <= 4.3:
                ph = 1.5375 - 0.125 * initial_ph
            elif 4.3 < initial_ph <= 5.0:
                ph = 5.9757 - 1.157 * initial_ph
            elif 5.0 < initial_ph <= 6.5:
                ph = 0.546125 - 0.071225 * initial_ph
        elif temperature == 150.0:
            if 3.5 <= initial_ph <= 3.8:
                ph = 1
            elif 3.8 < initial_ph <= 5.0:
                ph = 17.634 - 7.0945 * initial_ph + 0.715 * initial_ph**2
            elif 5.0 < initial_ph <= 6.5:
                ph = 0.037
        return ph

    @staticmethod
    def _convert_celsius_to_kelvin(temperature):
        """
        Convert temperature from Celsius to Kelvin.

        Parameters:
        temperature (float): Temperature in Celsius

        Returns:
        float: Temperature in Kelvin
        """
        return units.c_to_k(temperature)


class _DLD_opt:
    """DLD corrosion model (de Waard, Lotz, Dugstad, 1995).

    Reference: "Influence of liquid flow velocity on CO2 corrosion: A semi-emperical model"
    https://www.osti.gov/biblio/106125
    """

    def __init__(self):
        """Initialize DLD corrosion optimization model."""
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

        A = self.parameters["A"]
        B = self.parameters["B"]
        C = self.parameters["C"]

        return 10 ** (A - B / temperature_kelvin + C * math.log10(co2_fugacity))

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

        D = self.parameters["D"]

        return D * (velocity**0.8 / pipe_diameter**0.2) * co2_fugacity

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
        # print(fugacity_coefficient * co2_partial_pressure)
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
        return units.c_to_k(temperature_celsius)


class _DLM_opt:
    """The original DLM (C. de Waard; U. Lotz; D. E. Milliams, 1991) model.

    Model proposed in the article "Predictive Model
    for CO2 Corrosion Engineering in Wet Natural Gas Pipelines"
    https://doi.org/10.5006/1.3585212
    """

    def __init__(self):
        """Initialize DLM corrosion optimization model."""
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
        u (dict): Dictionary containing the required
        parameters for corrosion rate calculation.

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

        temperature_kelvin = self._convert_celsius_to_kelvin(temperature_celsius)

        A = self.parameters["A"]
        B = self.parameters["B"]
        C = self.parameters["C"]

        corrosion_rate = 10 ** (
            A - B / temperature_kelvin + C * math.log10(co2_fugacity)
        ) * self._calculate_scaling_factor(temperature_celsius, co2_fugacity)
        return corrosion_rate

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
        float: Fugacity of CO2 in [bar]
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
        scaling_factor = 10 ** (2400 / temperature_kelvin - 0.6 * math.log10(co2_fugacity) - 6.7)

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
        return units.c_to_k(temperature_celsius)


class _NORSOK_opt:
    """NORSOK standard M-506 "CO2 Corrosion Rate Calculation Model".

    Spreadsheet-based software model is available online (https://www.standard.no).
    """

    def __init__(self):
        """Initialize NORSOK corrosion optimization model."""
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
        self.output["corrosion_rate"] = self.calculate_corrosion_rate(u)

    def get_output(self):
        """Get output of the model."""
        return self.output

    def calculate_corrosion_rate(self, u):
        """
        Calculate the corrosion rate based on various parameters.

        Parameters:
        u (dict): Dictionary containing the required
        parameters for corrosion rate calculation.

        Returns:
        float: Corrosion rate in mm/year
        """
        co2_fraction = u.get("co2_fraction", None)
        co2_partial_pressure = u.get("co2_partial_pressure", None)

        pressure = u["pressure"]
        temperature = u["temperature"]
        water_density = u["water_density"]
        water_viscosity = u["water_viscosity"]
        water_flow_rate = u["water_flow_rate"]
        pipe_roughness = self.parameters["roughness"]
        pipe_diameter = self.parameters["diameter"]
        bicarb_concentration = u["bicarb_concentration"]
        ionic_strength = u["ionic_strength"]

        co2_fugacity = self._calculate_co2_fugacity(
            pressure=pressure,
            temperature_celsius=temperature,
            co2_fraction=co2_fraction,
            co2_partial_pressure=co2_partial_pressure,
        )

        shear_stress = self._calculate_shear_stress(
            water_density, water_viscosity, pipe_diameter, pipe_roughness, water_flow_rate
        )

        if co2_partial_pressure is not None:
            co2_pressure = co2_partial_pressure
        elif co2_fraction is not None:
            co2_pressure = co2_fraction * pressure
        else:
            # If neither is provided, we can’t proceed
            raise ValueError("Either 'co2_partial_pressure' or 'co2_fraction' must be provided.")
        ph = self._calculate_ph(
            temperature, pressure, co2_pressure, bicarb_concentration, ionic_strength
        )

        ph_fixed = self._adjust_ph_for_temperature(temperature, ph)
        kt = self._interpolate_kt_value(temperature)
        shear_factor = (shear_stress / 19) ** (0.146 + 0.0324 * math.log10(co2_fugacity))
        co2_fugacity_factor = co2_fugacity**0.62

        A = self.parameters["A"]

        corrosion_rate = A * kt * co2_fugacity_factor * shear_factor * ph_fixed
        return corrosion_rate

    def _interpolate_kt_value(self, temperature):
        """
        Calculate the interpolated Kt value for a given temperature.

        Parameters:
        temperature (float): The temperature for which the Kt value is to be calculated.

        Returns:
        float: The interpolated Kt value.
        """
        temperatures = (5, 15, 20, 40, 60, 80, 90, 120, 150)
        kt_values = (0.42, 1.59, 4.762, 8.927, 10.695, 9.949, 6.250, 7.770, 5.203)
        pos = bisect.bisect_left(temperatures, temperature)

        if pos == 0:
            return kt_values[0]
        if pos == len(temperatures):
            return kt_values[-1]

        temp_l = temperatures[pos - 1]
        temp_u = temperatures[pos]
        kt_lower = kt_values[pos - 1]
        kt_upper = kt_values[pos]

        return kt_lower + (temperature - temp_l) * (kt_upper - kt_lower) / (temp_u - temp_l)

    def _calculate_ph(
        self,
        temperature,
        pressure,
        co2_pressure,
        bicarb_concentration,
        ionic_strength,
        calc_of_ph=10,
    ):
        """
        Calculate the pH of the solution.

        Parameters:
        temperature (float): Temperature in Celsius
        pressure (float): Pressure in the system [bar]
        co2_pressure (float): CO2 partial pressure [bar]
        bicarb_concentration (float): Bicarbonate concentration [mg/l]
        ionic_strength (float): Ionic strength [g/l]
        calc_of_ph (int): Number of pH calculations to perform [-]

        Returns:
        float: Calculated pH
        """
        bicarb = bicarb_concentration / (1000 * 61.2)
        temp_fahrenheit = units.c_to_f(temperature)
        temp_kelvin = self._convert_celsius_to_kelvin(temperature)
        ionic_strength_adjusted = ionic_strength / 58.44
        pressure_psi = units.bar_to_psi(pressure)

        h0 = (14.5 / 1.00258) * 10 ** (
            -(
                2.27
                + 0.00565 * temp_fahrenheit
                - 0.00000806 * temp_fahrenheit**2
                + 0.075 * ionic_strength_adjusted
            )
        )
        k0 = 0.00258
        k1 = 387.6 * 10 ** (
            -(
                6.41
                - 0.001594 * temp_fahrenheit
                + 0.00000852 * temp_fahrenheit**2
                - 0.0000307 * pressure_psi
                - 0.4772 * ionic_strength_adjusted**0.5
                + 0.118 * ionic_strength_adjusted
            )
        )
        k2 = 10 ** (
            -(
                10.61
                - 0.00497 * temp_fahrenheit
                + 0.00001331 * temp_fahrenheit**2
                - 0.00002624 * pressure_psi
                - 1.166 * ionic_strength_adjusted**0.5
                + 0.3466 * ionic_strength_adjusted
            )
        )
        ksp_feco3 = 10 ** (-(10.13 + 0.0182 * temperature))
        kw = 10 ** (-(29.3868 - 0.0737549 * temp_kelvin + 7.47881 * 10 ** (-5) * temp_kelvin**2))

        for _ in range(calc_of_ph):
            sat_pH_coeff = (
                0 if calc_of_ph == 1 else (2 * ksp_feco3 / (h0 * k0 * k1 * k2 * co2_pressure))
            )
            iterations = 0
            h_ion = 10**-3.5 if co2_pressure <= 20 else 10**-2.9

            while True:
                f_h_ion = (
                    sat_pH_coeff * h_ion**4
                    + h_ion**3
                    + bicarb * h_ion**2
                    - h_ion * (k1 * k0 * h0 * co2_pressure + kw)
                    - 2 * k1 * k2 * k0 * h0 * co2_pressure
                )
                f_prime_h_ion = (
                    4 * sat_pH_coeff * h_ion**3
                    + 3 * h_ion**2
                    + 2 * bicarb * h_ion
                    - (k1 * k0 * h0 * co2_pressure + kw)
                )
                h_ion_next = h_ion - f_h_ion / f_prime_h_ion

                if abs(h_ion_next - h_ion) < 10**-6 * h_ion or iterations >= 100:
                    break
                h_ion = h_ion_next
                iterations += 1

            if h_ion > 0:
                ph = round(-(math.log(h_ion) / 2.3026), 2)
            else:
                ph = 99.99
        return ph

    def _calculate_co2_fugacity(
        self, pressure, temperature_celsius, co2_fraction=None, co2_partial_pressure=None
    ):
        """Calculate the fugacity of CO2.

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

    @staticmethod
    def _calculate_shear_stress(
        water_density, water_viscosity, pipe_diameter, pipe_roughness, water_flowrate
    ):
        """Calculate the shear stress in the pipeline for a multiphase flow of oil, gas, and water.

        Returns:
        float: Shear stress in the pipeline (Pa)
        """
        # Made this way for potential 3 phase flow.
        # Convert flow rates from m3/hr to m3/s
        water_flow_rate = units.m3day_to_m3s(water_flowrate)

        # Calculate superficial velocities (m/s)
        area = math.pi * (pipe_diameter / 2) ** 2  # area in m2
        v_sw = water_flow_rate / area
        v_m = v_sw

        # Calculate mixture properties
        density_mixture = (water_density * water_flow_rate) / (water_flow_rate)
        viscosity_mixture = (water_viscosity * water_flow_rate) / (water_flow_rate) / 1000
        friction_factor = 0.001375 * (
            1
            + (
                20000 * pipe_roughness / pipe_diameter
                + 10**6 * viscosity_mixture / (v_m * pipe_diameter * density_mixture)
            )
            ** 0.33
        )
        shear_stress = 0.5 * density_mixture * friction_factor * v_m**2
        return shear_stress

    @staticmethod
    def _adjust_ph_for_temperature(temperature, initial_ph):
        """
        Calculate pH fixed for temperature.

        Parameters:
        temperature (float): Temperature in Celsius
        initial_ph (float): Initial pH value

        Returns:
        float: pH value fixed for temperature
        """
        ph = 7
        if temperature == 5.0:
            if 3.5 <= initial_ph <= 4.6:
                ph = 2.0676 + 0.2309 * initial_ph
            elif 4.6 < initial_ph <= 6.5:
                ph = 4.342 - 1.061 * initial_ph + 0.0708 * initial_ph**2
        elif temperature == 15.0:
            if 3.5 <= initial_ph <= 4.6:
                ph = 2.0676 - 0.2309 * initial_ph
            elif 4.6 < initial_ph <= 6.5:
                ph = 4.986 - 1.191 * initial_ph + 0.0708 * initial_ph**2
        elif temperature == 20.0:
            if 3.5 <= initial_ph <= 4.6:
                ph = 2.0676 - 0.2309 * initial_ph
            elif 4.6 < initial_ph <= 6.5:
                ph = 5.1885 - 1.2353 * initial_ph + 0.0708 * initial_ph**2
        elif temperature == 40.0:
            if 3.5 <= initial_ph <= 4.6:
                ph = 2.0676 - 0.2309 * initial_ph
            elif 4.6 < initial_ph <= 6.5:
                ph = 5.1885 - 1.2353 * initial_ph + 0.0708 * initial_ph**2
        elif temperature == 60.0:
            if 3.5 <= initial_ph <= 4.6:
                ph = 1.836 - 0.1818 * initial_ph
            elif 4.6 < initial_ph <= 6.5:
                ph = 15.444 - 6.1291 * initial_ph + 0.8204 * initial_ph**2 - 0.0371 * initial_ph**3
        elif temperature == 80.0:
            if 3.5 <= initial_ph <= 4.6:
                ph = 2.6727 - 0.3636 * initial_ph
            elif 4.6 < initial_ph <= 6.5:
                ph = 331.68 * math.exp(-1.2618 * initial_ph)
        elif temperature == 90.0:
            if 3.5 <= initial_ph <= 4.57:
                ph = 3.1355 - 0.4673 * initial_ph
            elif 4.57 < initial_ph <= 5.62:
                ph = 21254 * math.exp(-2.1811 * initial_ph)
            elif 5.62 < initial_ph <= 6.5:
                ph = 0.4014 - 0.0538 * initial_ph
        elif temperature == 120.0:
            if 3.5 <= initial_ph <= 4.3:
                ph = 1.5375 - 0.125 * initial_ph
            elif 4.3 < initial_ph <= 5.0:
                ph = 5.9757 - 1.157 * initial_ph
            elif 5.0 < initial_ph <= 6.5:
                ph = 0.546125 - 0.071225 * initial_ph
        elif temperature == 150.0:
            if 3.5 <= initial_ph <= 3.8:
                ph = 1
            elif 3.8 < initial_ph <= 5.0:
                ph = 17.634 - 7.0945 * initial_ph + 0.715 * initial_ph**2
            elif 5.0 < initial_ph <= 6.5:
                ph = 0.037
        return ph

    @staticmethod
    def _convert_celsius_to_kelvin(temperature):
        """
        Convert temperature from Celsius to Kelvin.

        Parameters:
        temperature (float): Temperature in Celsius

        Returns:
        float: Temperature in Kelvin
        """
        return units.c_to_k(temperature)


def co2_corrosion_rate(
    model: Literal["NORSOK", "DLM", "DLD"],
    *,
    fitted: bool = False,
    temperature: float,
    pressure: float,
    water_flow_rate: float,
    water_density: float = 1000,
    water_viscosity: float = 0.001,
    diameter: float = 0.1,
    roughness: float = 0.00005,
    co2_fraction: float | None = None,
    co2_partial_pressure: float | None = None,
    bicarb_concentration: float = 0.268,
    ionic_strength: float = 71,
    coefficients: dict[str, float] | None = None,
) -> float:
    """Evaluate the original CO2 correlation through an SI boundary.

    Parameters
    ----------
    model : str
        NORSOK M-506, DLM (1991), or DLD (1995).
    fitted : bool
        Select the original fitted variant; coefficients default to published values.
    temperature, pressure : float
        Temperature [K] and absolute pressure [Pa].
    water_flow_rate, water_density, water_viscosity : float
        Liquid flow [m3/s], density [kg/m3], viscosity [Pa s].
    diameter, roughness : float
        Pipe inner diameter and roughness [m].
    co2_fraction, co2_partial_pressure : float, optional
        Gas mole fraction [-] or CO2 partial pressure [Pa]; pressure takes precedence.
    bicarb_concentration, ionic_strength : float
        Bicarbonate and salt concentrations [kg/m3].
    coefficients : dict, optional
        Fitted correlation constants in their original empirical basis.

    Returns
    -------
    float
        Wall penetration rate [mm/year].
    """
    classes = {"NORSOK": (_NORSOK, _NORSOK_opt), "DLM": (_DLM, _DLM_opt), "DLD": (_DLD, _DLD_opt)}
    if model not in classes:
        raise ValueError(f"Unknown corrosion model {model!r}")
    defaults = {
        "NORSOK": {"A": 1},
        "DLM": {"A": 5.8, "B": 1710, "C": 0.67},
        "DLD": {"A": 4.93, "B": 1119, "C": 0.58, "D": 2.45},
    }
    corr = classes[model][int(fitted)]()
    corr.update_parameters(
        dict(diameter=diameter, roughness=roughness, **(defaults[model] | (coefficients or {})))
    )
    u = dict(
        temperature=units.k_to_c(temperature),
        pressure=units.pa_to_bar(pressure),
        water_flow_rate=units.m3s_to_m3day(water_flow_rate),
        flow_rate=water_flow_rate,
        water_density=water_density,
        water_viscosity=units.pas_to_cp(water_viscosity),
        co2_fraction=co2_fraction,
        bicarb_concentration=units.kgm3_to_mgl(bicarb_concentration),
        ionic_strength=ionic_strength,
    )
    if co2_partial_pressure is not None:
        u["co2_partial_pressure"] = units.pa_to_bar(co2_partial_pressure)
    # NOTE(refactor): NORSOK retains exact-temperature pH branches and fallback 7.
    corr.calculate_output(u, None)
    return float(corr.get_output()["corrosion_rate"])


def wall_loss(rates_mm_per_year, durations_s) -> np.ndarray:
    """Integrate WIMS interval rates [mm/year] over durations [s] to cumulative loss [mm]."""
    rates = np.asarray(rates_mm_per_year, dtype=float)
    durations = np.asarray(durations_s, dtype=float)
    if rates.shape != durations.shape or np.any(durations < 0):
        raise ValueError("Rates and nonnegative durations must have equal shapes")
    return np.cumsum(rates * durations / units.SECONDS_PER_YEAR)
