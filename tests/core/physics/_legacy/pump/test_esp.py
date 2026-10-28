"""Unit tests for ESP pump model."""

import unittest

from gemini.core.physics._legacy.pump.esp import ESP

ESP_PARAMS = {
    "pump_name": "HC27000",
    "no_stages": 12,
    "head_coeff": [
        83.08389282,
        -0.000460444,
        -1.19e-07,
        1.69e-11,
        -6.36e-16,
        6.69e-21,
    ],
    "power_coeff": [
        10.02089977,
        -0.000160233,
        6.52e-08,
        -2.13e-12,
        1.71e-17,
        1.38e-23,
    ],
}

ESP_INPUT = {
    "pump_freq": 60,  # Hz
    "pump_flow": 200 / 3600,  # m3/h to m3/s
}


class TestESP(unittest.TestCase):
    """Test cases for ESP pump model."""

    def setUp(self):
        """Initialize the configuration and initial parameters."""
        self.esp_instance = ESP()
        self.esp_instance.update_parameters(dict(ESP_PARAMS))

    def test_esp_calculation(self):
        """Test ESP pump calculation."""
        self.esp_instance.calculate_output(dict(ESP_INPUT))
        y = self.esp_instance.get_output()

        self.assertAlmostEqual(y["pump_head"] / 1e5, 23.37, delta=0.01)  # bar
        self.assertAlmostEqual(y["pump_power"] / 1e3, 183.89, delta=0.01)  # kW
        self.assertAlmostEqual(y["pump_eff"], 70.53, delta=0.01)  # %

    def test_esp_missing_coefficient_power(self):
        """Test ESP pump with missing power coefficient."""
        self.esp_instance.parameters["power_coeff"] = [0, 0, 0, 0, 0, 0]
        self.esp_instance.calculate_output(dict(ESP_INPUT))
        y = self.esp_instance.get_output()
        self.assertAlmostEqual(y["pump_power"] / 1e3, 0, delta=0.01)  # kW
        self.assertAlmostEqual(y["pump_eff"], 0, delta=0.01)  # %

    def test_initialize_and_update_state_are_noop_for_static_model(self):
        """Test StaticModel no-state defaults on ESP."""
        self.assertIsNone(self.esp_instance.initialize_state())
        self.assertIsNone(self.esp_instance.update_state(dict(ESP_INPUT)))

    def test_get_output_returns_copy(self):
        """Test output getter protects model internals from external mutation."""
        self.esp_instance.calculate_output(dict(ESP_INPUT))
        out = self.esp_instance.get_output()
        out["pump_head"] = -1
        self.assertNotEqual(self.esp_instance.get_output()["pump_head"], -1)

    def test_update_parameters_requires_required_keys(self):
        """Test required ESP parameters are validated."""
        model = ESP()
        with self.assertRaises(KeyError):
            model.update_parameters({"no_stages": 12})

    def test_update_parameters_requires_six_coefficients(self):
        """Test ESP polynomial coefficients length validation."""
        model = ESP()
        invalid = dict(ESP_PARAMS)
        invalid["head_coeff"] = [1, 2, 3]
        with self.assertRaises(ValueError):
            model.update_parameters(invalid)

    def test_calculate_output_requires_required_inputs(self):
        """Test required ESP runtime inputs are validated."""
        with self.assertRaises(KeyError):
            self.esp_instance.calculate_output({"pump_freq": 60})
