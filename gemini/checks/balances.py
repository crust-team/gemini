"""Energy and mass ledgers over the time series of a finished run."""

import numpy as np

from gemini.types.shapes import check, value
from gemini.utils.strings import join_path

ENERGY_TOLERANCE = 1e-9
"""Smallest negative power [W] still read as zero."""

MASS_TOLERANCE = 1e-12
"""Smallest negative mass flow [kg/s] still read as zero."""

_NONNEGATIVE_ENERGY = ("fuel", "power_in", "power_out")
"""The energy columns that are nonnegative; ``loss_out`` and ``heat_accumulation`` are signed."""


def _columns(results, wanted):
    """Return the result columns for which ``wanted(path, field)`` holds, as a frame."""
    frame = results.to_frame()
    names = [
        join_path(path, field)
        for path, fields in results.names().items()
        for field in fields
        if wanted(path, field)
    ]
    return frame[names]


def _nonnegative(name, values, tolerance, unit, absent):
    """Judge that every value is finite-or-missing and at least ``-tolerance`` in ``unit``."""
    limit = value(tolerance, unit)
    if values.shape[1] == 0:
        return check(name, None, value(None, unit, absent), limit)
    array = values.to_numpy(dtype=float)
    if np.isnan(array).all():
        return check(name, None, value(None, unit, "every value is missing"), limit)
    smallest = float(np.nanmin(array))
    passed = bool(smallest >= -tolerance and not np.isinf(array).any())
    return check(name, passed, value(smallest, unit), limit)


def energy_balance(results):
    """Check the energy ledger of a finished run: the energy outputs have their sign.

    Results store the leaf output columns, not the streams that cross the leaves, so the
    enthalpy closure of ``gemini.modules._utils.balance.energy_balance`` (sum in minus sum out
    per call) cannot be recomputed from them. This check covers the ledger of
    ``ENERGY_INPUTS`` and ``ENERGY_OUTPUTS`` of that module: it reads every leaf column named
    ``electricity``, ``fuel``, ``heat_absorbed``, ``heat_loss``, ``heat_supplied`` or
    ``electricity_generated`` and checks that each value is finite or missing and not negative
    beyond the tolerance (``heat_accumulation`` is signed and is not judged).

    Parameters
    ----------
    results : Results
        A finished run; the plant is not needed.

    Returns
    -------
    dict
        ``{name: "energy_balance", passed, value, limit}``: ``value`` is the smallest of those
        powers [W] over all columns and ticks, ``limit`` is 1e-9 W and ``passed`` is whether
        ``value >= -limit`` with no infinite value. ``passed`` is ``None``, with a ``reason`` in
        ``value``, when no such column, or no value, exists.
    """
    values = _columns(results, lambda path, field: field in _NONNEGATIVE_ENERGY)
    return _nonnegative(
        "energy_balance", values, ENERGY_TOLERANCE, "W", "results have no energy output column"
    )


def mass_balance(results):
    """Check the mass-flow ledger of a finished run: no mass flow is negative or infinite.

    Results store leaf output columns, not the streams that cross the leaves, so the mass
    closure of ``gemini.modules._utils.balance.mass_balance`` (inflow minus outflow per call)
    cannot be recomputed from them. This check covers the leaf outputs whose unit in
    ``results.units`` is kg/s (for example a degasser's ``gas_mass_flow``): each value must be
    finite or missing and not negative beyond the tolerance.

    Parameters
    ----------
    results : Results
        A finished run; the plant is not needed.

    Returns
    -------
    dict
        ``{name: "mass_balance", passed, value, limit}``: ``value`` is the smallest mass flow
        [kg/s], ``limit`` 1e-12 kg/s. ``passed`` is ``None``, with a ``reason`` in ``value``, when
        no output has the unit kg/s, or no value exists.
    """
    values = _columns(results, lambda path, field: results.unit(path, field) == "kg/s")
    absent = "results have no output in kg/s"
    return _nonnegative("mass_balance", values, MASS_TOLERANCE, "kg/s", absent)
