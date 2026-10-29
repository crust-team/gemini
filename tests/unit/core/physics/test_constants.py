"""Physical constants keep their historical values."""

from gemini.core.physics import constants, hydraulics


def test_constant_values():
    """Gravity, the Beggs–Brill US basis and the CO2 molar mass match the originals."""
    assert constants.G == 9.81
    assert constants.G_FT == 32.17405
    assert constants.CO2_MOLAR_MASS == 0.04401
    assert constants.MIN_PATH_PRESSURE == 0.001
    assert hydraulics.hydrostatic_dp(1, 1) == constants.G
