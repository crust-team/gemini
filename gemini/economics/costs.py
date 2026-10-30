"""Investment and annual operating cost of a plant run."""

from dataclasses import dataclass

from gemini.analysis.series import energy, leaf_total, window_seconds
from gemini.economics.assumptions import require, resolve
from gemini.economics.emissions import source_energies
from gemini.economics.outcome import outcome
from gemini.errors import ValidationError
from gemini.modules.demand import CoolingConsumer, HeatConsumer
from gemini.physics.units import SECONDS_PER_YEAR
from gemini.types.cost import total_cost

NO_COST = (
    "no module declares a cost: a module declares it by defining capex() that returns a Cost, "
    "and no built-in module does"
)
"""The reason when a plant has no declared cost."""


@dataclass(frozen=True)
class Annual:
    """Energies per year [J/year], scaled from the window of a run."""

    heat: float
    cold: float
    fuel: float
    grid: float


def annual_energies(plant, results):
    """Return the heat and cold delivered and the fuel and grid electricity drawn per year.

    The run is taken as representative of a year: each energy over the window of the results is
    scaled by one year over that window. The heat is the ``heat_supplied`` of the plant's
    ``HeatConsumer`` leaves and the cold the ``heat_absorbed`` of its ``CoolingConsumer`` leaves;
    a plant without such a leaf delivers none. A tick without a value adds no energy.
    """
    frame = results.to_frame()
    seconds = window_seconds(results)
    scale = SECONDS_PER_YEAR / seconds.sum()
    heat = leaf_total(plant, frame, "heat_supplied", HeatConsumer)
    cold = leaf_total(plant, frame, "heat_absorbed", CoolingConsumer)
    fuel, grid = source_energies(results)
    return Annual(
        heat=0.0 if heat is None else energy(heat, seconds) * scale,
        cold=0.0 if cold is None else energy(cold, seconds) * scale,
        fuel=fuel * scale,
        grid=grid * scale,
    )


def capex(plant, assumptions=None):
    """Return the investment of a plant: the sum of the costs its modules declare.

    One implementation: ``gemini.types.cost.total_cost``. A module declares its cost by
    defining ``capex()`` that returns a ``Cost``; no built-in module does, so a plant of built-in
    modules has none, and nothing is estimated or defaulted.

    Parameters
    ----------
    plant : Module
        The plant whose modules and descendants declare costs.
    assumptions : Assumptions, optional
        Only its ``currency`` is used, to state the unit when the plant has no declared cost.

    Returns
    -------
    dict
        ``{value, unit, reason, price_year, source}`` as plain JSON. ``value`` is the investment
        in the currency of the costs (``unit``), with their ``price_year`` and ``source``. With
        no declared cost ``value``, ``price_year`` and ``source`` are ``None`` and ``reason``
        says so. Costs in different currencies or price years raise ``ConfigurationError``.
    """
    cost = total_cost(plant)
    if cost is None:
        return outcome(None, resolve(assumptions).currency, NO_COST, price_year=None, source=None)
    return outcome(cost.capex, cost.currency, None, price_year=cost.price_year, source=cost.source)


def _bill(assumptions, annual):
    """Return the yearly cost of the grid electricity and the fuel; a needed price must be given."""
    electricity = fuel = 0.0
    if annual.grid > 0:
        electricity = annual.grid * require(assumptions, "electricity_price")
    if annual.fuel > 0:
        fuel = annual.fuel * require(assumptions, "fuel_price")
    return {"electricity": electricity, "fuel": fuel}


def opex(plant, results, assumptions=None):
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
        ``electricity_price`` and ``fuel_price`` [currency/J], needed only for an energy that the
        run draws; a missing needed price raises ``ValidationError`` (code ``missing_value``).

    Returns
    -------
    dict
        ``{value, unit, reason, components}`` with ``unit`` the cost currency per year and
        ``components`` ``{fixed, variable, electricity, fuel}`` in that unit. With no declared
        cost ``value`` is ``None`` with the ``reason``, and only ``electricity`` and ``fuel``
        are given. A currency in ``assumptions`` other than the cost's raises
        ``ValidationError``.
    """
    assumptions = resolve(assumptions)
    cost = total_cost(plant)
    annual = annual_energies(plant, results)
    bill = _bill(assumptions, annual)
    if cost is None:
        return outcome(None, f"{assumptions.currency}/year", NO_COST, components={**bill})
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
    return outcome(sum(components.values()), f"{cost.currency}/year", None, components=components)
