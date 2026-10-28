"""ESP reference checks, fitting and drift monitoring (TNO 2022 R11363)."""

import numpy as np
import pytest

from gemini.components.pumps import ESP
from gemini.core.base.stream import Stream
from gemini.core.physics import units

ESP_PARAMS = {
    "pump_type": "HC27000",
    "no_stages": 12,
    "head_coeff": [
        83.08389282,
        -0.000460444,
        -1.19e-07,
        1.69e-11,
        -6.36e-16,
        6.69e-21,
    ],
    "power_coeff": [
        10.02089977,
        -0.000160233,
        6.52e-08,
        -2.13e-12,
        1.71e-17,
        1.38e-23,
    ],
}


def test_original_nonzero_power_reference():
    """Preserve the original 200 m3/h, 60 Hz reference beyond the zero-power example."""
    output, _ = ESP(ESP_PARAMS).compute(
        {"frequency": 60}, {"suction": Stream(m_dot=units.m3h_to_m3s(200) * 1000, T=300, p=100000)}
    )
    assert units.pa_to_bar(output.head) == pytest.approx(23.37, abs=0.01)
    assert output.power == pytest.approx(183890, abs=10)
    assert output.efficiency == pytest.approx(0.7053, abs=0.0001)


def test_fit_recovers_curve_and_health_threshold():
    """Synthetic curve fitting predicts withheld operating points and flags measured drift."""
    pump = ESP(ESP_PARAMS)
    flows = np.linspace(0.01, 0.06, 20)
    freq = np.linspace(40, 60, 20)
    heads = [pump.head_function(q, f) for q, f in zip(flows, freq)]
    fitted = ESP.fit_head_coefficients(flows, freq, heads, 12)
    other = ESP(dict(ESP_PARAMS, head_coeff=fitted))
    assert other.head_function(0.037, 53) == pytest.approx(pump.head_function(0.037, 53), rel=1e-9)
    out, _ = pump.compute({"frequency": 60}, {"suction": Stream(m_dot=40, T=300, p=1e5)})
    assert not pump.health(out, {"power": out.power}).alarm
    assert pump.health(out, {"power": out.power * 1.11}).alarm
    assert ESP.fit_head_correction([1, 2, 3], [3, 5, 7]) == pytest.approx((2, 1))
    assert len(pump.head_curve(50)) == 50
