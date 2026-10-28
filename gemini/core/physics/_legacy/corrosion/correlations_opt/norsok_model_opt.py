"""NORSOK corrosion model optimization module."""

import bisect
import math

from gemini.core.physics._legacy.model_abstract import StaticModel


class NORSOK(StaticModel):
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
        temp_fahrenheit = temperature * 1.8 + 32
        temp_kelvin = self._convert_celsius_to_kelvin(temperature)
        ionic_strength_adjusted = ionic_strength / 58.44
        pressure_psi = pressure * 14.503774

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
        water_flow_rate = water_flowrate / (3600 * 24)

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
        return temperature + 273.15
