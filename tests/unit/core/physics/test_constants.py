"""Physical constants keep their historical values."""

from gemini import ops
from gemini.core.physics import constants, hydraulics
from gemini.ops import Constant


def test_constant_values():
    """Gravity, the Beggs–Brill US basis and the CO2 molar mass match the originals."""
    assert float(constants.G) == 9.81
    assert float(constants.G_FT) == 32.17405
    assert float(constants.CO2_MOLAR_MASS) == 0.04401
    assert float(constants.MIN_PATH_PRESSURE) == 0.001
    assert hydraulics.hydrostatic_dp(1, 1) == float(constants.G)


def test_every_constant_is_a_named_constant_object():
    """Each module-level constant is a ``Constant`` named like its variable."""
    for name in ("G", "G_FT", "CO2_MOLAR_MASS", "MIN_PATH_PRESSURE"):
        constant = getattr(constants, name)
        assert isinstance(constant, Constant) and constant.name == name


def test_path_pressure_floor_is_a_plain_float():
    """The marched pressure never leaks the ``Constant`` object of the floor."""
    assert type(max(1.0, float(constants.MIN_PATH_PRESSURE))) is float
    assert type(ops.maximum(constants.MIN_PATH_PRESSURE, -5.0)) is float
