"""Unit tests for CO2 corrosion model."""

import math
import unittest

from gemini.core.physics._legacy.corrosion.co2_corrosion import CO2Corrosion

NORSOK_WELL_PARAMS = {
    "roughness": 50e-6,
    "corrosion_model": "NORSOK",
    "diameter": 0.1,
}

DLD_WELL_PARAMS = {
    "corrosion_model": "DLD",
    "diameter": 0.1,
}

DLM_WELL_PARAMS = {"corrosion_model": "DLM"}


class TestCO2Corrosion(unittest.TestCase):
    """Test CO2 corrosion calculations."""

    @staticmethod
    def _calculate_corrosion_rate(parameters, inputs):
        model = CO2Corrosion()
        model.update_parameters(dict(parameters))
        model.calculate_output(dict(inputs), None)
        return model.get_output()["corrosion_rate"]

    def test_get_corrosion_rate_norsok(self):
        """Test NORSOK corrosion rate calculation."""
        u = {
            "co2_fraction": 0.1,  # CO2 concentration [-]
            "pressure": 3,  # Total pressure [bar]
            "temperature": 40,  # Temperature [C]
            "water_density": 1024,  # kg/m3
            "water_viscosity": 0.5469,  # cp
            "water_flow_rate": 1000,  # m3/day
            "bicarb_concentration": 268,  # mg/l
            "ionic_strength": 71,  # g/l
            "calc_of_ph": 10,  # [-]
        }
        corrosion_rate = self._calculate_corrosion_rate(NORSOK_WELL_PARAMS, u)
        expected_corrosion_rate = 1.412  # [mm/year]
        self.assertAlmostEqual(corrosion_rate, expected_corrosion_rate, places=3)

    def test_get_corrosion_rate_dld(self):
        """Test DLD corrosion rate calculation."""
        u = {
            "co2_fraction": 1,  # CO2 concentration [-]
            "pressure": 3,  # Total pressure [bar]
            "temperature": 50,  # Temperature [C]
            "flow_rate": 1 * math.pi * (DLD_WELL_PARAMS["diameter"] ** 2) / 4.0,
        }
        corrosion_rate = self._calculate_corrosion_rate(DLD_WELL_PARAMS, u)
        expected_corrosion_rate = 9.6  # [mm/year]
        self.assertAlmostEqual(corrosion_rate, expected_corrosion_rate, places=1)

    def test_get_corrosion_rate_dlm(self):
        """Test DLM corrosion rate calculation."""
        u = {
            "co2_fraction": 1,  # CO2 concentration [-]
            "pressure": 3,  # Total pressure [bar]
            "temperature": 50,  # Temperature [C]
        }
        corrosion_rate = self._calculate_corrosion_rate(DLM_WELL_PARAMS, u)
        expected_corrosion_rate = 6.7  # [mm/year]
        self.assertAlmostEqual(corrosion_rate, expected_corrosion_rate, places=1)
