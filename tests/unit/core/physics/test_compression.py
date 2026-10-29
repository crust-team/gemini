"""Ideal-gas compression relations and their domain checks."""

import pytest

from gemini.core.physics import compression
from gemini.errors import PhysicsRangeError


def test_isentropic_and_actual_stage_temperatures():
    """Air (k = 1.4) at a pressure ratio of 8 from 300 K reaches 543.4 K isentropically."""
    ideal = compression.isentropic_outlet_temperature(300, 8, 1.4)
    assert ideal == pytest.approx(543.43, abs=0.01)
    assert compression.stage_outlet_temperature(300, 8, 1.4, 0.8) == pytest.approx(
        300 + (ideal - 300) / 0.8
    )
    assert compression.stage_outlet_temperature(300, 1, 1.4, 0.8) == 300


def test_multistage_work_splits_the_ratio_equally():
    """N intercooled stages do N times the work of one stage at the N-th root ratio."""
    one = compression.specific_compression_work(300, 4, 1.4, 1005, 0.8, 1)
    two = compression.specific_compression_work(300, 16, 1.4, 1005, 0.8, 2)
    assert two == pytest.approx(2 * one)
    assert two < compression.specific_compression_work(300, 16, 1.4, 1005, 0.8, 1)
    assert compression.specific_compression_work(300, 1, 1.4, 1005, 0.8, 3) == 0


@pytest.mark.parametrize(
    "arguments, match",
    [
        ((300, 0.5, 1.4, 1005, 0.8, 1), "pressure_ratio = 0.5"),
        ((0, 2, 1.4, 1005, 0.8, 1), "inlet_temperature = 0"),
        ((300, 2, 1.0, 1005, 0.8, 1), "heat_capacity_ratio = 1.0"),
        ((300, 2, 1.4, 1005, 0, 1), "isentropic_efficiency = 0"),
        ((300, 2, 1.4, 0, 0.8, 1), "specific_heat = 0"),
        ((300, 2, 1.4, 1005, 0.8, 0), "stages = 0"),
    ],
)
def test_out_of_domain_inputs_raise(arguments, match):
    """Expansion, nonpositive temperatures and invalid gas or machine data raise."""
    with pytest.raises(PhysicsRangeError, match=match):
        compression.specific_compression_work(*arguments)
