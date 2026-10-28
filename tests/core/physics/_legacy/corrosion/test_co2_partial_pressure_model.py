"""Unit tests for CO2 partial pressure model."""

import unittest

from gemini.core.physics._legacy.corrosion.correlation.co2_partial_pressure_model import (
    CO2PartialPressureModel,
)


class TestCO2PartialPressureModel(unittest.TestCase):
    """Test cases for CO2 partial pressure model."""

    def setUp(self):
        """Initialize the configuration and initial parameters."""
        self.co2_model = CO2PartialPressureModel()
        self.u = {
            "co2_mol_fraction": 0.1882,  # CO2 mol fraction in a gas phase[-]
            "gas_pressure": 1,  # Total Gas Pressure at sample P and T[bar]
            "gas_water_ratio": 0.4224,  # GWR [-]
            "gas_density": 1.027,  # Gas-water mixture density [kg/m3]
            "gas_molecular_weight": 22.955,  # Gas-water molecular weight [g/mol]
            "temperature_sample": 20,  # Temperature of a sample [C]
            "temperature_system": 85,  # System Temperature [C]
        }

    def test_get_co2_partial_pressure(self):
        """Test CO2 partial pressure calculation."""
        # Test data taken from WEP CO2 Partial Pressure model.
        result_dissolved_co2 = self.co2_model._get_CO2_solubility_in_liquid(
            self.u["co2_mol_fraction"], self.u["temperature_sample"], self.u["gas_pressure"]
        )
        result_gas_phase_co2 = self.co2_model._get_CO2_solubility_in_gas(
            self.u["co2_mol_fraction"],
            self.u["gas_water_ratio"],
            self.u["gas_density"],
            self.u["gas_molecular_weight"],
        )
        self.co2_model.calculate_output(self.u, None)
        result_co2_partial_pressure = self.co2_model.get_output()["CO2 Partial Pressure [bar]"]

        expected_dissolved_co2 = 0.007245
        expected_gas_phase_co2 = 0.003557
        expected_co2_partial_pressure = 1.2398
        self.assertAlmostEqual(result_dissolved_co2, expected_dissolved_co2, places=3)
        self.assertAlmostEqual(result_gas_phase_co2, expected_gas_phase_co2, places=3)
        self.assertAlmostEqual(result_co2_partial_pressure, expected_co2_partial_pressure, places=3)

    def test_output_has_expected_field(self):
        """Test output field presence and positivity."""
        self.co2_model.calculate_output(self.u, None)
        out = self.co2_model.get_output()
        self.assertIn("CO2 Partial Pressure [bar]", out)
        self.assertGreater(out["CO2 Partial Pressure [bar]"], 0)
