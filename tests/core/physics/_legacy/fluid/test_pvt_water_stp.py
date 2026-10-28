"""Unit tests for PVT water STP model."""

import unittest

from gemini.core.physics._legacy.fluid.pvt_water_stp import PVTConstantSTP


class TestPVTWaterSTP(unittest.TestCase):
    """Test cases for PVT water STP model."""

    def test_get_pvt(self):
        """Test PVT water STP calculation."""
        pvt_instance = PVTConstantSTP()

        P = 1e5
        T = 15 + 273.15
        rho_g, rho_l, gmf, eta_g, eta_l, cp_g, cp_l, K_g, K_l, sigma = pvt_instance.get_pvt(P, T)

        self.assertEqual(rho_g, pvt_instance.parameters["RHOG"])
        self.assertEqual(rho_l, 1000)
        self.assertEqual(gmf, pvt_instance.parameters["GMF"])
        self.assertEqual(eta_g, pvt_instance.parameters["VISG"])
        self.assertEqual(eta_l, pvt_instance.parameters["VISL"])
        self.assertEqual(cp_g, pvt_instance.parameters["CPG"])
        self.assertEqual(cp_l, pvt_instance.parameters["CPL"])
        self.assertEqual(K_g, pvt_instance.parameters["TCG"])
        self.assertEqual(K_l, pvt_instance.parameters["TCL"])
        self.assertEqual(sigma, pvt_instance.parameters["SIGMA"])
