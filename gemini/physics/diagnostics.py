"""Health-scoring relations shared by the modules: drift, bounded score, margin, limit test.

These are plain ratio formulas, not heat or flow physics; they sit here so that every module
that scores a measurement against a prediction uses the same expression.
"""

from gemini import ops

DRIFT_FLOOR = 1e-12
"""Smallest prediction magnitude used as a drift denominator, so a zero prediction is finite."""

DEFAULT_DRIFT_THRESHOLD = 0.10
"""Relative drift [-] of a measurement from its prediction that raises an alarm by default."""

DEFAULT_DECLINE_THRESHOLD = 0.15
"""Fractional decline [-] of a reservoir productivity or injectivity that alarms by default."""

DEFAULT_FOULING_THRESHOLD = 0.15
"""Fractional loss [-] of apparent conductance that alarms as fouling by default."""


@ops.physics
def relative_drift(measured: float, predicted: float) -> float:
    """Return the relative deviation of a measurement from its prediction.

    Parameters
    ----------
    measured, predicted : float
        Measured and predicted value, in the same unit.

    Returns
    -------
    float
        ``(measured - predicted) / max(|predicted|, DRIFT_FLOOR)`` [-]; finite for a zero
        prediction.

    Notes
    -----
    Plain relative error; the floor ``DRIFT_FLOOR`` only avoids a division by zero.
    """
    return (measured - predicted) / ops.maximum(ops.abs(predicted), DRIFT_FLOOR)


@ops.physics
def bounded_score(ratio: float) -> float:
    """Return a ratio clipped to [0, 1], a health score.

    Parameters
    ----------
    ratio : float
        Measured over reference value [-].

    Returns
    -------
    float
        ``min(1, max(0, ratio))`` [-].

    Notes
    -----
    One is a healthy unit, zero a failed one; no published source, a scoring convention.
    """
    return ops.minimum(1, ops.maximum(0, ratio))


@ops.physics
def remaining_margin(ratio: float) -> float:
    """Return the margin left before a ratio reaches one.

    Parameters
    ----------
    ratio : float
        Used over allowed value [-], for example a drift over its threshold.

    Returns
    -------
    float
        ``max(0, 1 - ratio)`` [-]; one for no use, zero at or beyond the limit.

    Notes
    -----
    Scoring convention without a published source.
    """
    return ops.maximum(0, 1 - ratio)


@ops.physics
def below_limit(ratio: float, threshold: float) -> bool:
    """Return whether a ratio fell by more than the threshold.

    Parameters
    ----------
    ratio : float
        Measured over reference value [-], one when healthy.
    threshold : float
        Allowed fractional loss [-], in (0, 1].

    Returns
    -------
    bool
        ``ratio < 1 - threshold``.

    Notes
    -----
    Alarm convention for a decline or fouling test, without a published source.
    """
    return ratio < 1 - threshold
