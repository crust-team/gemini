"""CO2 phase-partition checks from the original WEP sample reference."""

import json
from pathlib import Path

import pytest

from gemini.core.physics import chemistry, units

GOLDEN = json.loads((Path(__file__).parents[3] / "fixtures/golden_values.json").read_text())


def test_reference_solubilities():
    """Original mol/l references are expressed as mol/m3 in the new API."""
    assert chemistry.co2_solubility_liquid(0.1882, 293.15, 100000) == pytest.approx(
        7.245, abs=0.001
    )
    assert chemistry.co2_solubility_gas(0.1882, 0.4224, 1.027, 0.022955) == pytest.approx(
        3.557, abs=0.001
    )


def test_henry_constant_reference_and_temperature_dependence():
    """0.0385 mol/l/bar at 293.15 K; solubility falls as temperature rises."""
    assert chemistry.henry_constant(293.15) == pytest.approx(0.0385 * 0.01)
    assert chemistry.henry_constant(350) < chemistry.henry_constant(293.15)


def test_chemistry_golden():
    """CO2 partition calculation preserves the original partial pressure."""
    value = chemistry.co2_partial_pressure(
        co2_fraction=0.1882,
        gas_pressure=units.bar_to_pa(1),
        gas_water_ratio=0.4224,
        gas_density=1.027,
        gas_molecular_weight=0.022955,
        temperature_sample=units.c_to_k(20),
        temperature_system=units.c_to_k(85),
    )
    assert value == pytest.approx(
        units.bar_to_pa(GOLDEN["chemistry"]["expected"]["CO2 Partial Pressure [bar]"]), rel=1e-9
    )
