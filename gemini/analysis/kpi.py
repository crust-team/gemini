"""The plant KPIs under fixed names: ``gm.kpi.compute`` and ``gm.kpi.names``.

Every KPI is read from the leaf columns of a finished run (``results.to_frame()``) through the
declared outputs of the plant's leaves, so it needs no extra recording. A tick where a needed
column has no value (a skipped or failed row) is left out of that KPI's sums and peaks.
"""

from dataclasses import dataclass
from typing import Any

import numpy as np

from gemini.analysis.series import energy, leaf_total, results_total, window_seconds
from gemini.modules.demand import CoolingConsumer, HeatConsumer
from gemini.types.shapes import value


@dataclass(frozen=True)
class _Series:
    """The plant-level power series [W] the KPIs share, each ``None`` when the plant lacks it."""

    seconds: np.ndarray
    heat: Any
    heat_unmet: Any
    cold: Any
    cold_unmet: Any
    electricity: Any


def _read(plant, results):
    """Return the shared series of a run."""
    frame = results.to_frame()
    sensible = leaf_total(plant, frame, "unmet_sensible", CoolingConsumer)
    latent = leaf_total(plant, frame, "unmet_latent", CoolingConsumer)
    return _Series(
        seconds=window_seconds(results),
        heat=leaf_total(plant, frame, "heat_supplied", HeatConsumer),
        heat_unmet=leaf_total(plant, frame, "unmet_demand", HeatConsumer),
        cold=leaf_total(plant, frame, "heat_absorbed", CoolingConsumer),
        cold_unmet=None if sensible is None or latent is None else sensible + latent,
        electricity=results_total(results, frame, "electricity"),
    )


def _coverage(delivered, unmet, seconds, consumer):
    """Return delivered energy over demanded energy, or a reason when it is undefined."""
    if delivered is None or unmet is None:
        return None, f"the plant has no {consumer}"
    demand = delivered + unmet
    demanded = energy(demand, seconds)
    if demanded <= 0:
        return None, "the demand is zero over the window"
    return energy(delivered.where(demand.notna()), seconds) / demanded, None


def _peak(delivered, consumer):
    """Return the largest delivered power, or a reason when there is none."""
    if delivered is None:
        return None, f"the plant has no {consumer}"
    if delivered.notna().sum() == 0:
        return None, "no tick has a delivered power"
    return float(delivered.max()), None


def _heating_coverage(series):
    return _coverage(series.heat, series.heat_unmet, series.seconds, "HeatConsumer")


def _cooling_coverage(series):
    return _coverage(series.cold, series.cold_unmet, series.seconds, "CoolingConsumer")


def _peak_heat(series):
    return _peak(series.heat, "HeatConsumer")


def _peak_cold(series):
    return _peak(series.cold, "CoolingConsumer")


def _cop(series):
    if series.heat is None:
        return None, "the plant has no HeatConsumer"
    if series.electricity is None:
        return None, "no leaf declares an electricity output"
    consumed = energy(series.electricity.where(series.heat.notna()), series.seconds)
    if consumed <= 0:
        return None, "no electricity is consumed over the window"
    return energy(series.heat.where(series.electricity.notna()), series.seconds) / consumed, None


__all__ = ["compute", "names"]

_KPIS = {
    "heating_coverage": ("-", _heating_coverage),
    "cooling_coverage": ("-", _cooling_coverage),
    "cop": ("-", _cop),
    "peak_heat": ("W", _peak_heat),
    "peak_cold": ("W", _peak_cold),
}
"""Each KPI name with its unit and the function that computes ``(value, reason)``."""


def names():
    """Return the fixed KPI names, in the order ``compute`` reports them."""
    return list(_KPIS)


def compute(plant, results):
    """Return the KPIs of a finished run as ``{name: {value, unit}}``, plain JSON.

    Parameters
    ----------
    plant : Module
        The plant that produced ``results``.
    results : Results
        A finished ``simulate`` or ``replay``.

    Returns
    -------
    dict
        One entry per name of ``names()``. ``value`` is a number in ``unit``, or ``None``
        with the ``reason`` text when the run cannot give it (never a guess). The definitions,
        with E(x) = sum over ticks of x * tick duration [J]:

        - ``heating_coverage`` [-] = E(heat_supplied) / E(heat_supplied + unmet_demand) summed
          over the plant's ``HeatConsumer`` leaves: the share of the demanded heat delivered.
        - ``cooling_coverage`` [-] = E(heat_absorbed) / E(heat_absorbed + unmet_sensible +
          unmet_latent) over the ``CoolingConsumer`` leaves.
        - ``cop`` [-] = E(heat_supplied of the HeatConsumer leaves) / E(electricity of every
          leaf): heat delivered per unit of electricity consumed. Cooling is not counted.
        - ``peak_heat`` [W] = the largest tick sum of ``heat_supplied`` over the
          ``HeatConsumer`` leaves (delivered power, not the demand peak).
        - ``peak_cold`` [W] = the largest tick sum of ``heat_absorbed`` over the
          ``CoolingConsumer`` leaves.

    A plant without a consumer leaf, for example the doublet heat plant, gives ``None`` for the
    KPIs that need one.
    """
    series = _read(plant, results)
    values = {}
    for name, (unit, compute) in _KPIS.items():
        number, reason = compute(series)
        values[name] = value(number, unit, reason)
    return values
