"""The circuit rates and outlet temperatures that the two sorption machines share."""

import pytest

from gemini.core.modules.heat import _sorption as sorption
from gemini.core.types.flows import Stream
from gemini.errors import PhysicsRangeError


def test_rates_are_the_heat_capacity_rate_of_each_inlet():
    """Each port gets ``m_dot * cp_l`` of its stream."""
    inlets = {"hot": Stream(m_dot=2.0, T=350.0, p=1e5), "cold": Stream(m_dot=0.0, T=300.0, p=1e5)}
    rates = sorption.rates("unit", inlets)
    assert rates["hot"] == inlets["hot"].heat_capacity_rate()
    assert rates["cold"] == 0.0


def test_rates_reject_negative_flow_naming_the_port():
    """A negative mass flow raises with the module path and the port."""
    inlets = {"hot": Stream(m_dot=-1.0, T=350.0, p=1e5)}
    with pytest.raises(PhysicsRangeError, match=r"^unit: hot.m_dot = -1.0 kg/s; expected >= 0$"):
        sorption.rates("unit", inlets)


def test_outlet_temperature_adds_the_duty_over_the_rate():
    """No duty keeps the inlet temperature; a duty shifts it by duty / rate."""
    stream = Stream(m_dot=1.0, T=350.0, p=1e5)
    assert sorption.outlet_T(stream, 4000.0, 0.0) == 350.0
    assert sorption.outlet_T(stream, 4000.0, -2000.0) == 349.5
