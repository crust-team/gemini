"""Investment and annual operating cost of a plant run."""

from dataclasses import dataclass

import numpy as np

from gemini.errors import ValidationError
from gemini.evaluate.outcome import currency_of, reported, unavailable
from gemini.evaluate.series import edge_total, energy, useful_cold, useful_heat, window_seconds
from gemini.modules.grids import ChemicalGrid, ElectricityGrid, GasGrid, WasteGrid
from gemini.run.assumptions import resolve
from gemini.types.cost import total_cost
from gemini.types.shapes import value
from gemini.units import SECONDS_PER_YEAR

NO_COST = (
    "no module declares a cost: a module declares it by defining capex(assumptions) that returns "
    "a Cost"
)
"""The reason when a plant has no declared cost."""


@dataclass(frozen=True)
class Annual:
    """Energies per year [J/year], scaled from the window of a run."""

    heat: float
    cold: float
    fuel: float
    grid: float
    waste: float
    chemical: float


def annual_energies(plant, results):
    """Return the useful heat and cold and the gas and electricity bought per year.

    Useful is at most the demand: a heat the users had no need of costs money and pays nothing.

    The run is taken as representative of a year: each energy over the window of the results is
    scaled by one year over that window. Everything is read from the ports of the edge modules; a
    plant without such a module has none of it. A tick without a value adds no energy.
    """
    frame = results.to_frame()
    seconds = window_seconds(results)
    scale = SECONDS_PER_YEAR / seconds.sum()
    totals = (
        useful_heat(plant, frame),
        useful_cold(plant, frame),
        edge_total(plant, frame, "gas_out.chemical_flow", GasGrid),
        edge_total(plant, frame, "net_import", ElectricityGrid),
        edge_total(plant, frame, "waste_in.mass_flow", WasteGrid),
        edge_total(plant, frame, "chemical_out.mass_flow", ChemicalGrid),
    )
    return Annual(*(0.0 if total is None else energy(total, seconds) * scale for total in totals))


def capex(plant, assumptions=None, on_error="raise"):
    """Return the investment of a plant: the sum of the costs its modules declare.

    One implementation: ``gemini.types.cost.total_cost``. A module declares its cost by defining
    ``capex(assumptions)`` that returns a ``Cost`` from its own design values and the cost factors
    of ``assumptions``. A factor without a value raises ``ValidationError`` (code
    ``missing_assumption``), and nothing is estimated.

    Parameters
    ----------
    plant : Module
        The plant whose modules and descendants declare costs.
    assumptions : Assumptions, optional
        The cost factors, the ``currency`` and the ``cost_price_year``.
    on_error : {"raise", "record"}, optional
        A value the inputs cannot give raises; ``"record"`` makes it ``None`` with a ``reason``.

    Returns
    -------
    dict
        ``{value, unit, price_year, source}`` as plain JSON. ``value`` is the investment in the
        currency of the costs (``unit``), with their ``price_year`` (a value in ``year``) and
        ``source``. Costs in different currencies or price years raise ``ValidationError``.
    """

    def compute():
        given = resolve(assumptions)
        cost = total_cost(plant, given)
        if cost is None:
            return unavailable(given.currency, NO_COST, on_error)
        year = value(cost.price_year, "year")
        return value(cost.capex, cost.currency, price_year=year, source=cost.source)

    return reported(on_error, currency_of(assumptions), compute)


def mean_price(assumptions, carrier):
    """Return the price of ``carrier`` in SI, as one number over the run."""
    return float(np.mean(assumptions.price(carrier)))


def _bill(assumptions, annual):
    """Return the yearly bills of what the plant buys and discards; a needed price must be given."""
    electricity = fuel = 0.0
    if annual.grid > 0:
        electricity = annual.grid * mean_price(assumptions, "electricity")
    if annual.fuel > 0:
        fuel = annual.fuel * mean_price(assumptions, "gas")
    waste = chemical = 0.0
    if annual.waste > 0:
        waste = annual.waste * mean_price(assumptions, "waste_disposal")
    if annual.chemical > 0:
        chemical = annual.chemical * mean_price(assumptions, "chemical")
    return {"electricity": electricity, "fuel": fuel, "waste": waste, "chemical": chemical}


def _components(amounts, unit):
    """Return each amount of a cost as a value."""
    return {name: value(amount, unit) for name, amount in amounts.items()}


def opex(plant, results, assumptions=None, on_error="raise"):
    """Return the annual operating cost of a plant run.

    The sum of the declared fixed cost [currency/year], the declared variable cost
    [currency/J] times the heat and cold delivered per year, and the yearly bill of the grid
    electricity and the fuel at the assumed prices. The energies per year are those of
    ``annual_energies``: the run is scaled to a year.

    Parameters
    ----------
    plant : Module
        The plant whose modules declare costs.
    results : Results
        A finished run of the plant.
    assumptions : Assumptions, optional
        the prices of ``electricity`` and ``gas``, needed only for an
        energy that the run buys; a missing needed price raises ``ValidationError`` (code
        ``missing_assumption``). Co-produced gas costs nothing.
    on_error : {"raise", "record"}, optional
        A value the inputs cannot give raises; ``"record"`` makes it ``None`` with a ``reason``.

    Returns
    -------
    dict
        ``{value, unit, components}`` with ``unit`` the cost currency per year and ``components``
        ``{fixed, variable, electricity, fuel}``, each a value in that unit. With no declared
        cost and ``on_error="record"``, ``value`` is ``None`` with a ``reason``, and only
        ``electricity`` and ``fuel`` are given. A currency in ``assumptions`` other than the cost's
        raises ``ValidationError``.
    """
    unit = f"{currency_of(assumptions)}/year"
    return reported(on_error, unit, lambda: _opex(plant, results, assumptions, on_error))


def _opex(plant, results, assumptions, on_error):
    """Return the annual operating cost; ``on_error`` applies to a plant without a cost."""
    assumptions = resolve(assumptions)
    cost = total_cost(plant, assumptions)
    annual = annual_energies(plant, results)
    bill = _bill(assumptions, annual)
    if cost is None:
        unit = f"{assumptions.currency}/year"
        return unavailable(unit, NO_COST, on_error, components=_components(bill, unit))
    if cost.currency != assumptions.currency:
        raise ValidationError(
            f"assumptions.currency = {assumptions.currency!r}; expected the cost currency "
            f"{cost.currency!r}",
            path="assumptions.currency",
        )
    components = {
        "fixed": cost.opex_fixed,
        "variable": cost.opex_variable * (annual.heat + annual.cold),
        **bill,
    }
    unit = f"{cost.currency}/year"
    return value(sum(components.values()), unit, components=_components(components, unit))
