"""Fits of model parameters to measurements: pump curves, reservoir pressure, exchanger UA.

Modules hold the parameters a fit produces; the fit itself lives here, on plain NumPy arrays or
through the physics functions.
"""

import numpy as np

from gemini.errors import InsufficientDataError, UnknownCorrelationError
from gemini.physics import constants, heat_transfer, units

CURVE_COEFFICIENTS = 6
"""Number of ascending polynomial coefficients of an ESP curve, so at least so many flows."""


def fit_head_coefficients(flows, frequencies, heads, stage_count) -> list[float]:
    """Fit the six ascending US-basis ESP head coefficients from SI observations.

    Parameters
    ----------
    flows, frequencies, heads : array_like
        Volume flows [m3/s], frequencies [Hz] and heads [Pa], at least six matching observations
        with six distinct flows.
    stage_count : int
        Number of pump stages, positive.

    Returns
    -------
    list of float
        Coefficients of ``physics.pumps.head``: ft of head per stage at 60 Hz with flow in bbl/day.

    Notes
    -----
    Least-squares polynomial of degree five through the observations reduced to one stage at the
    reference frequency by the affinity law ``H ~ f^2``.
    """
    q, f, h = (np.asarray(value, dtype=float) for value in (flows, frequencies, heads))
    if q.shape != f.shape or q.shape != h.shape or q.ndim != 1 or len(q) < CURVE_COEFFICIENTS:
        raise InsufficientDataError("ESP: at least six matching observations required")
    if stage_count <= 0 or np.any(f <= 0) or np.any(q < 0) or not np.isfinite([q, f, h]).all():
        raise InsufficientDataError("ESP: fitting requires finite positive stages and frequencies")
    x = units.m3s_to_bbl_per_day(q)
    y = units.pa_to_ft_head(h) / (stage_count * (f / constants.ESP_REFERENCE_FREQUENCY) ** 2)
    if len(np.unique(x)) < CURVE_COEFFICIENTS:
        raise InsufficientDataError("ESP: six distinct flow values are required")
    degree = CURVE_COEFFICIENTS - 1
    return np.polynomial.Polynomial.fit(x, y, degree).convert().coef.tolist()


def fit_head_correction(measured, theoretical) -> tuple[float, float]:
    """Fit the affine correction ``theoretical = slope * measured + offset`` [-, Pa].

    Parameters
    ----------
    measured, theoretical : array_like
        Measured and theoretical heads [Pa], at least two finite pairs with distinct measurements.

    Returns
    -------
    tuple of float
        Least-squares slope [-] and offset [Pa].
    """
    x, y = (np.asarray(value, dtype=float) for value in (measured, theoretical))
    if x.shape != y.shape or len(x) < 2 or not np.isfinite([x, y]).all() or np.var(x) == 0:
        raise InsufficientDataError("ESP: two or more finite, distinct measurements required")
    slope = np.sum((x - x.mean()) * (y - y.mean())) / np.sum((x - x.mean()) ** 2)
    return float(slope), float(y.mean() - slope * x.mean())


def estimate_reservoir_pressure(flows, bottomhole_pressures) -> tuple[float, float]:
    """Fit the reservoir pressure [Pa] and the R-squared [-] from flow observations.

    Parameters
    ----------
    flows, bottomhole_pressures : array_like
        Volume flows [m3/s] and bottomhole pressures [Pa], at least two matching finite samples
        with nonzero flows.

    Returns
    -------
    tuple of float
        The slope of the least-squares line ``p_bh / Q = p_res (1 / Q) + b``, which is the
        reservoir pressure of a linear inflow relation, and the R-squared of the line.
    """
    q, p = (np.asarray(value, dtype=float) for value in (flows, bottomhole_pressures))
    if (
        q.shape != p.shape
        or q.ndim != 1
        or len(q) < 2
        or np.any(q == 0)
        or not np.isfinite([q, p]).all()
    ):
        raise InsufficientDataError(
            "Reservoir pressure estimation needs at least two matching finite, nonzero samples"
        )
    x, y = 1 / q, p / q
    if np.ptp(x) == 0 or np.ptp(y) == 0:
        raise InsufficientDataError("Reservoir pressure regression requires variation")
    coefficients = np.polyfit(x, y, 1)
    residual = y - np.poly1d(coefficients)(x)
    r_squared = 1 - np.sum(residual**2) / np.sum((y - np.mean(y)) ** 2)
    return float(coefficients[0]), float(r_squared)


def estimate_conductance(
    hot_in_T,
    hot_out_T,
    cold_in_T,
    cold_out_T,
    m_dot_hot,
    m_dot_cold,
    *,
    cp_hot=heat_transfer.DEFAULT_CP,
    cp_cold=heat_transfer.DEFAULT_CP,
    arrangement="counterflow",
):
    """Estimate the apparent UA [W/K] of an exchanger from measured temperatures and mass flows.

    Temperatures are in K, mass flows in kg/s and heat capacities in J/kg/K. Raises
    ``InsufficientDataError`` when the measurements cannot determine UA: a stopped stream, hot and
    cold duties that disagree by more than 5 %, or no positive LMTD; see
    ``heat_transfer.apparent_conductance``.
    """
    if arrangement not in {"counterflow", "parallel"}:
        raise UnknownCorrelationError(
            f"HeatExchanger: unknown arrangement {arrangement!r}; expected counterflow or parallel"
        )
    apparent, code, hot_duty, cold_duty, delta = heat_transfer.apparent_conductance(
        arrangement,
        hot_in_T,
        hot_out_T,
        cold_in_T,
        cold_out_T,
        m_dot_hot,
        m_dot_cold,
        cp_hot,
        cp_cold,
    )
    if code == heat_transfer.NONPOSITIVE_INPUT:
        raise InsufficientDataError(
            "HeatExchanger: mass flows and heat capacities must be positive"
        )
    if code == heat_transfer.DISAGREEING_DUTIES:
        raise InsufficientDataError(
            f"HeatExchanger: hot/cold duties must agree within 5%; got {hot_duty} W and "
            f"{cold_duty} W"
        )
    if code == heat_transfer.NO_LMTD:
        raise InsufficientDataError(f"HeatExchanger: positive LMTD required; got {delta} K")
    return apparent
