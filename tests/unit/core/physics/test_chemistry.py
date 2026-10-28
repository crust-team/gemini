"""CO2 phase-partition checks from the original WEP sample reference."""

import pytest

from gemini.core.physics import chemistry


def test_reference_solubilities():
    """Original mol/l references are expressed as mol/m3 in the new API."""
    assert chemistry.co2_solubility_liquid(0.1882, 293.15, 100000) == pytest.approx(
        7.245, abs=0.001
    )
    assert chemistry.co2_solubility_gas(0.1882, 0.4224, 1.027, 0.022955) == pytest.approx(
        3.557, abs=0.001
    )
