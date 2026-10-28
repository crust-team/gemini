"""First-law and zero-flow boiler limits."""

import pytest

from gemini.core.base.stream import Stream
from gemini.core.modules.heat import Boiler


def test_capacity_balance_and_no_cooling():
    """Capacity caps heat, energy input accounts for efficiency, and the boiler never cools."""
    c = Boiler(dict(fuel="gas", capacity=100000, efficiency=0.8))
    s = Stream(m_dot=10, T=300, p=1e6)
    out, streams = c({"setpoint_T": 360}, {"inlet": s})
    assert out.capped and out.duty == 100000 and out.fuel_or_power == 125000
    assert (streams["outlet"].T - s.T) * s.m_dot * 4217.4 == pytest.approx(out.duty)
    assert streams["outlet"].m_dot == s.m_dot and streams["outlet"].p == s.p
    out, _ = c({"setpoint_T": 290}, {"inlet": s})
    assert out.duty == 0 and out.outlet_T == 300
    out, _ = c({"setpoint_T": 360}, {"inlet": s.with_(m_dot=0)})
    assert out.duty == 0 and out.outlet_T == 300
