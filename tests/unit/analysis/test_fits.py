"""Fits of model parameters to measurements."""

import numpy as np
import pytest

from gemini import analysis
from gemini.errors import InsufficientDataError, UnknownCorrelationError
from gemini.physics import pumps

CURVE = [83.08389282, -0.000460444, -1.19e-07, 1.69e-11, -6.36e-16, 6.69e-21]


def test_fit_head_coefficients_recovers_the_curve():
    """A fit of synthetic heads predicts a withheld point of the same curve."""
    flows = np.linspace(0.01, 0.06, 20)
    frequencies = np.linspace(40, 60, 20)
    heads = [pumps.head(q, f, 12, CURVE) for q, f in zip(flows, frequencies)]
    fitted = analysis.fit_head_coefficients(flows, frequencies, heads, 12)
    assert pumps.head(0.037, 53, 12, fitted) == pytest.approx(
        pumps.head(0.037, 53, 12, CURVE), rel=1e-9
    )


def test_fit_head_coefficients_refuses_too_few_or_invalid_observations():
    """Fewer than six points, repeated flows or a nonpositive frequency are insufficient."""
    with pytest.raises(InsufficientDataError, match="six matching"):
        analysis.fit_head_coefficients([1, 2], [50, 50], [1, 2], 12)
    with pytest.raises(InsufficientDataError, match="six distinct"):
        analysis.fit_head_coefficients([0.01] * 6, [50] * 6, list(range(6)), 12)
    with pytest.raises(InsufficientDataError, match="finite positive"):
        analysis.fit_head_coefficients([0.01] * 6, [0] * 6, list(range(6)), 12)


def test_fit_head_correction_is_the_least_squares_line():
    """Exact points give the slope and the offset of their line."""
    assert analysis.fit_head_correction([1, 2, 3], [3, 5, 7]) == pytest.approx((2, 1))
    with pytest.raises(InsufficientDataError, match="distinct"):
        analysis.fit_head_correction([1, 1], [3, 5])


def test_estimate_reservoir_pressure_finds_the_linear_inflow_pressure():
    """Points of ``p_bh = p_res + b Q`` give ``p_res`` and an R-squared of one."""
    flows = np.array([0.01, 0.02, 0.04])
    pressure, r_squared = analysis.estimate_reservoir_pressure(flows, 2e7 - 1e8 * flows)
    assert pressure == pytest.approx(2e7)
    assert r_squared == pytest.approx(1)
    with pytest.raises(InsufficientDataError, match="nonzero"):
        analysis.estimate_reservoir_pressure([0, 1], [1, 2])


def test_estimate_conductance_is_the_mean_duty_over_the_lmtd():
    """Equal terminal differences of 40 K give the duty over 40 K."""
    conductance = analysis.estimate_conductance(
        350, 340, 300, 310, 10, 10, cp_hot=4000, cp_cold=4000
    )
    assert conductance == pytest.approx(10 * 4000 * 10 / 40)
    with pytest.raises(InsufficientDataError, match="agree"):
        analysis.estimate_conductance(350, 340, 300, 340, 10, 10)
    with pytest.raises(UnknownCorrelationError, match="arrangement"):
        analysis.estimate_conductance(350, 340, 300, 310, 10, 10, arrangement="cross")
