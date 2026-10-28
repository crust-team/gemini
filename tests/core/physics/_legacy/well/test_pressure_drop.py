"""Unit tests for well pressure drop model."""

import unittest

import numpy as np

from gemini.core.physics._legacy.fluid.pvt_water_stp import PVTConstantSTP
from gemini.core.physics._legacy.well.pressure_drop import DPDT


class TestDPDT(unittest.TestCase):
    """Test cases for well pressure drop model."""

    def _create_injection_model(self):
        well_param = dict()
        well_param["diameter"] = (
            np.array([6.366, 6.366, 9.95, 6.366, 3.92]) * 0.0254
        )  # casing diameter in [m]
        well_param["length"] = np.array([0, 148, 949, 1012, 218])  # well length in [m]
        well_param["angle"] = np.array([90, 90, 69.0, 44.4, 40.3]) * np.pi / 180
        well_param["roughness"] = np.array(
            [0.0003, 0.0003, 0.0003, 0.0003, 0.0003]
        )  # well roughness in [m]
        well_param["friction_correlation"] = "darcy_weisbach"
        well_param["friction_correlation_2p"] = "BeggsBrill"
        well_param["correction_factors"] = [1, 0]

        well_instance = DPDT()
        well_instance.update_parameters(well_param)
        well_instance.PVT = PVTConstantSTP()
        return well_instance

    def _create_production_model(self):
        well_param = dict()
        well_param["diameter"] = (
            np.array([8.535, 8.535, 8.535, 8.535, 8.535]) * 0.0254
        )  # casing diameter in [m]
        well_param["length"] = np.array([400, 600, 600, 400, 200])  # well length in [m]
        well_param["angle"] = np.array([90, 90, 90, 75, 60]) * np.pi / 180  # well angle in [rad]
        well_param["roughness"] = np.array(
            [0.01e-3, 0.01e-3, 0.01e-3, 0.01e-3, 0.01e-3]
        )  # well roughness in [m]
        well_param["friction_correlation"] = "darcy_weisbach"
        well_param["friction_correlation_2p"] = "BeggsBrill"
        well_param["correction_factors"] = [1, 0]

        well_instance = DPDT()
        well_instance.update_parameters(well_param)
        well_instance.PVT = PVTConstantSTP()
        return well_instance

    def test_calculate_bottomhole(self):
        """Test well pressure drop bottomhole calculation."""
        well_instance = self._create_injection_model()
        u = {
            "flowrate": -10 / 3600,  # m3/s
            "temperature": 61.5 + 273.15,  # K
            "pressure": 1e5,  # Pa
            "direction": "down",  # injection well
            "temperature_ambient": 20 + 273.15,  # K
        }
        well_instance.calculate_output(u, None)

        y = well_instance.get_output()
        self.assertAlmostEqual(y["pressuredrop_fric_output"], -6264.02, delta=0.01)

        u["flowrate"] = 0
        well_instance.calculate_output(u, None)
        y = well_instance.get_output()
        self.assertAlmostEqual(y["pressuredrop_fric_output"], 0, delta=0.01)

    def test_calculate_wellhead(self):
        """Test well pressure drop wellhead calculation."""
        well_instance = self._create_production_model()
        u = {
            "pressure": 250 * 1e5,  # Pa
            "temperature": 80 + 273.15,  # K
            "flowrate": 150 / 3600,  # m3/s
            "temperature_ambient": 20 + 273.15,
            "direction": "up",  # production well
            "correction_a": 1,
            "correction_b": 0,
        }
        well_instance.calculate_output(u, None)
        y = well_instance.get_output()

        self.assertAlmostEqual(y["pressure_output"], 3714980.20, delta=0.01)
        self.assertAlmostEqual(y["temperature_output"], 75.06 + 273.15, delta=0.01)

    def test_direction_is_case_insensitive(self):
        """Test normalized direction handling."""
        well_instance = self._create_production_model()
        u = {
            "pressure": 250 * 1e5,  # Pa
            "temperature": 80 + 273.15,  # K
            "flowrate": 150 / 3600,  # m3/s
            "temperature_ambient": 20 + 273.15,
            "direction": "UP",
        }
        well_instance.calculate_output(u, None)
        y = well_instance.get_output()
        self.assertAlmostEqual(y["pressure_output"], 3714980.20, delta=0.01)
