"""ESP reference checks, fitting and drift monitoring (TNO 2022 R11363)."""

import numpy as np
import pytest

import gemini as gm
from gemini import backends
from gemini.core.modules.pumps import ESP
from gemini.core.physics import units
from gemini.core.types.flows import Stream
from tests.fixtures.equivalence import assert_health_matches, assert_module_matches

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
    output = (
        ESP()
        .update_params(**ESP_PARAMS)(
            frequency=60,
            suction=Stream(m_dot=units.m3h_to_m3s(200) * 1000, T=300, p=100000),
        )
        .outputs
    )
    assert units.pa_to_bar(output.head) == pytest.approx(23.37, abs=0.01)
    assert output.power == pytest.approx(183890, abs=10)
    assert output.efficiency == pytest.approx(0.7053, abs=0.0001)


def test_fit_recovers_curve_and_health_threshold():
    """Synthetic curve fitting predicts withheld operating points and flags measured drift."""
    pump = ESP().update_params(**ESP_PARAMS)
    flows = np.linspace(0.01, 0.06, 20)
    freq = np.linspace(40, 60, 20)
    heads = [pump.head_function(q, f) for q, f in zip(flows, freq)]
    fitted = ESP.fit_head_coefficients(flows, freq, heads, 12)
    other = ESP().update_params(**dict(ESP_PARAMS, head_coeff=fitted))
    assert other.head_function(0.037, 53) == pytest.approx(pump.head_function(0.037, 53), rel=1e-9)
    result = pump(frequency=60, suction=Stream(m_dot=40, T=300, p=1e5))
    power = result.outputs.power
    assert not pump.health(result, {"power": power}).alarm
    assert pump.health(result, {"power": power * 1.11}).alarm
    assert ESP.fit_head_correction([1, 2, 3], [3, 5, 7]) == pytest.approx((2, 1))
    assert len(pump.head_curve(50)) == 50


def test_the_esp_alone_asks_for_a_plain_scope_under_float32_precision():
    """Float32 keeps Python floats next to the float32 coefficients; a stopped pump still runs."""
    esp = ESP().update_params(**ESP_PARAMS)
    stopped = dict(frequency=60, suction=Stream(m_dot=0.0, T=300, p=100000))
    assert esp._scalar_mode() == backends.WRAP
    reference = esp(**stopped).outputs.efficiency
    with gm.runtime.settings(precision="float32"):
        assert esp._scalar_mode() == backends.PLAIN
        assert esp(**stopped).outputs.efficiency == reference == 0.0
    assert backends.scope_mode() is None


def _health_rows(pump, flows_kg_s):
    return [pump(frequency=60, suction=Stream(m_dot=m_dot, T=300, p=1e5)) for m_dot in flows_kg_s]


def test_health_on_arrays_equals_one_call_per_row():
    """Worst key, drift, window and message of every row match, with and without drifts."""
    pump = ESP().update_params(**ESP_PARAMS, max_flow=0.05)
    results = _health_rows(pump, [20.0, 40.0, 40.0, 60.0, 30.0])
    outputs = [result.outputs for result in results]
    scales = [(1.0, 1.3), (1.2, 0.5), (1.0, 1.0), (0.8, 1.5), (1.05, 0.99)]
    measured = [
        {"power": out.power * a, "head": out.head * b, "discharge_pressure": out.discharge_pressure}
        for out, (a, b) in zip(outputs, scales)
    ]
    assert_health_matches(pump, results, measured)
    assert_health_matches(pump, results, [{"power": row["power"]} for row in measured])
    assert_health_matches(pump, results, [{} for _ in measured])


def test_traced_call_matches_one_call_per_row_on_every_backend():
    """Low, nominal and high flow, a trickle and a low frequency, on every backend."""
    rows = [
        dict(suction=Stream(m_dot=m_dot, T=300, p=1e5), frequency=frequency)
        for m_dot, frequency in ((5, 60), (60, 60), (200, 50), (500, 60), (1e-3, 60), (60, 35))
    ]
    assert_module_matches(ESP().update_params(**ESP_PARAMS), rows)
