"""CO2 emitted by a finished run, and the fuel and grid energy it draws."""

from types import SimpleNamespace

import numpy as np

from gemini.analysis.series import results_total, window_seconds
from gemini.economics.assumptions import require, resolve
from gemini.economics.outcome import reported
from gemini.modules.balance import emissions
from gemini.types.shapes import value

_LEDGER = ("electricity", "fuel", "electricity_generated")


def _weighted_energy(results, fuel_weight, grid_weight):
    """Return the sum over ticks of ``emissions`` with the given weights, times the tick length.

    ``emissions`` is ``fuel * fuel_weight + max(0, electricity - electricity_generated) *
    grid_weight`` over the leaf totals; weights of 1 and 0 give the fuel energy [J] and of 0 and
    1 the grid electricity energy [J]. A tick without a value adds nothing.
    """
    frame = results.to_frame()
    columns = {
        field: total.to_numpy(dtype=float)
        for field in _LEDGER
        if (total := results_total(results, frame, field)) is not None
    }
    total = SimpleNamespace(children={}, outputs=columns)
    rate = emissions({"": total}, fuel_weight, grid_weight)
    return float(np.nansum(rate * window_seconds(results)))


def source_energies(results):
    """Return the fuel energy and the grid electricity energy [J] drawn over the run.

    Grid electricity is the consumption not covered by on-site generation, tick by tick, as
    ``gemini.modules.balance.emissions`` counts it.
    """
    return _weighted_energy(results, 1.0, 0.0), _weighted_energy(results, 0.0, 1.0)


def co2(plant, results, assumptions=None, on_error="raise"):
    """Return the CO2 emitted over the run [kg] from the fuel burnt and the grid electricity.

    This is ``gemini.modules.balance.emissions`` summed over the ticks: fuel energy times
    ``fuel_emission_factor`` plus grid electricity energy times ``electricity_emission_factor``.
    On-site generation offsets consumption before grid electricity is counted and a surplus
    earns no credit. Gas vented by a ``Vent`` is not included.

    Parameters
    ----------
    plant : Module
        The plant of the run, as for every economics function; the columns alone give the value.
    results : Results
        A finished run; its leaf ``electricity``, ``fuel`` and ``electricity_generated`` columns
        are summed.
    assumptions : Assumptions, optional
        The emission factors [kg/J]. The default has the sourced fuel factor of natural gas and
        no electricity factor.
    on_error : {"raise", "record"}, optional
        A value the inputs cannot give raises; ``"record"`` makes it ``None`` with a ``reason``.

    Returns
    -------
    dict
        ``{value, unit, fuel_energy, grid_energy, window}``: ``value`` in kg over the window of
        the results; ``fuel_energy`` and ``grid_energy`` in J and ``window`` in s, each a value.
        Grid electricity drawn without ``electricity_emission_factor`` raises
        ``ValidationError`` (code ``missing_value``).
    """
    return reported(on_error, "kg", lambda: _co2(results, assumptions))


def _co2(results, assumptions):
    """Return the CO2 value of a run."""
    assumptions = resolve(assumptions)
    fuel, grid = source_energies(results)
    emitted = fuel * assumptions.fuel_emission_factor
    if grid > 0:
        emitted += grid * require(assumptions, "electricity_emission_factor")
    return value(
        emitted,
        "kg",
        fuel_energy=value(fuel, "J"),
        grid_energy=value(grid, "J"),
        window=value(float(window_seconds(results).sum()), "s"),
    )
