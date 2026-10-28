"""Original published corrosion reference values and fitted-model equivalence."""

import math

import pytest

from gemini.core.physics import corrosion, units


@pytest.mark.parametrize("model,expected", [("DLM", 6.7), ("DLD", 9.6)])
@pytest.mark.parametrize("fitted", [False, True])
def test_original_reference(model, expected, fitted):
    """Retain the original tests at 50 degC and 3 bar (de Waard–Lotz 1991/1995)."""
    value = corrosion.co2_corrosion_rate(
        model,
        fitted=fitted,
        temperature=units.c_to_k(50),
        pressure=units.bar_to_pa(3),
        co2_fraction=1,
        water_flow_rate=math.pi * 0.1**2 / 4,
        diameter=0.1,
    )
    assert value == pytest.approx(expected, abs=0.05)


def test_partial_pressure_and_unknown_model():
    """Explicit CO2 partial pressure equals fraction times total pressure."""
    common = dict(temperature=313.15, pressure=300000, water_flow_rate=0.01)
    a = corrosion.co2_corrosion_rate("DLM", co2_fraction=0.1, **common)
    b = corrosion.co2_corrosion_rate("DLM", co2_partial_pressure=30000, **common)
    assert a == pytest.approx(b, rel=1e-12)
    with pytest.raises(ValueError, match="Unknown corrosion"):
        corrosion.co2_corrosion_rate("missing", co2_fraction=0.1, **common)


def test_wims_remaining_wall_and_lifetime():
    """WIMS radial loss and linear lifetime retain deposition and missing-data limits."""
    assert corrosion.remaining_wall_thickness(0.1, 0.09, 0.002) == pytest.approx(0.008)
    assert corrosion.remaining_wall_thickness(0.1, 0.09, -0.002) == pytest.approx(0.012)
    assert corrosion.time_to_minimum_wall(0.008, 0.006, 1e-10) == pytest.approx(2e7)
    assert corrosion.time_to_minimum_wall(0.005, 0.006, 1e-10) == 0
    assert math.isinf(corrosion.time_to_minimum_wall(0.008, 0.006, 0))
    assert math.isnan(corrosion.time_to_minimum_wall(float("nan"), 0.006, 1e-10))
