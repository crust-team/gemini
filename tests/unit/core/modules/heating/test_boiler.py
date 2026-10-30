"""First-law and zero-flow boiler limits."""

import pytest

from gemini.core.modules.heating import Boiler
from gemini.core.types.flows import Stream
from tests.fixtures.equivalence import assert_module_matches


def test_capacity_balance_and_no_cooling():
    """Capacity caps heat, energy input accounts for efficiency, and the boiler never cools."""
    c = Boiler().update_params(fuel_type="gas", capacity=100000, efficiency=0.8)
    s = Stream(m_dot=10, T=300, p=1e6)
    result = c(temperature_setpoint=360, inlet=s)
    out, streams = result.outputs, result.outlets
    assert out.capped and out.duty == 100000 and out.fuel_or_power == 125000
    assert (streams["outlet"].T - s.T) * s.m_dot * 4217.4 == pytest.approx(out.duty)
    assert streams["outlet"].m_dot == s.m_dot and streams["outlet"].p == s.p
    out = c(temperature_setpoint=290, inlet=s).outputs
    assert out.duty == 0 and out.outlet_T == 300
    out = c(temperature_setpoint=360, inlet=s.with_(m_dot=0)).outputs
    assert out.duty == 0 and out.outlet_T == 300


@pytest.mark.parametrize("fuel_type", ["gas", "electric"])
def test_traced_call_matches_one_call_per_row(fuel_type):
    """Capped, uncapped, no-heating-needed and stopped rows trace and equal one call per row."""
    boiler = Boiler().update_params(fuel_type=fuel_type, capacity=100000, efficiency=0.8)
    rows = [
        dict(inlet=Stream(m_dot=m_dot, T=300, p=1e6), temperature_setpoint=setpoint)
        for m_dot, setpoint in [(10, 360), (1, 310), (10, 290), (0, 360), (2, 305)]
    ]
    assert_module_matches(boiler, rows)
