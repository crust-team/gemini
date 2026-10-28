"""Unit tests for reservoir inflow performance model."""

import unittest

from gemini.core.physics._legacy.reservoir.inflow_performance import IPR

RESERVOIR_PARAMS = {
    "reservoir_pressure": 300,
    "productivity_index": 5,
    "type": "production_reservoir",
}

RESERVOIR_INPUT = {"flow": 100}


class TestIPR(unittest.TestCase):
    """Test cases for reservoir inflow performance model."""

    def setUp(self):
        """Initialize the configuration and initial parameters."""
        self.res_instance = IPR()
        self.res_instance.update_parameters(dict(RESERVOIR_PARAMS))

    def test_calculate_bottomhole(self):
        """Test reservoir inflow performance calculation."""
        self.res_instance.calculate_output(dict(RESERVOIR_INPUT), None)
        y = self.res_instance.get_output()

        self.assertAlmostEqual(y["bottomhole_pressure"], 280, delta=0.01)

    def test_static_model_state_methods_are_noop(self):
        """Test IPR follows StaticModel no-state behavior."""
        self.assertIsNone(self.res_instance.initialize_state(None))
        self.assertIsNone(self.res_instance.update_state(dict(RESERVOIR_INPUT), None))
