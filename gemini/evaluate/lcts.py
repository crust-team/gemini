"""Levelised cost of thermal supply."""

from gemini.evaluate._utils.flows import Flows
from gemini.evaluate._utils.levelised import annualised
from gemini.evaluate._utils.outcome import reported, unavailable
from gemini.types.shapes import value


def lcts(plant, problem, results, discount_rate=None, lifetime=None, on_error="raise"):
    """Return the levelised cost of thermal supply [currency/J].

    ``annualised_cost / (heat + cold)``, the heat and the cold delivered per year as scaled from
    the run. One cost over both products, so it needs no ``heat_cost_share``. The parameters are
    those of ``annualised_cost``.

    Returns
    -------
    dict
        ``{value, unit, annualised_cost, heat, cold}``, the last three each a value, ``heat`` and
        ``cold`` in J/year; ``value`` in currency/J (multiply by 3.6e9 for currency/MWh). A plant
        that declares no cost, or a run that delivers neither heat nor cold, has no value.
    """
    return reported(
        on_error,
        f"{problem.assumptions.currency}/J",
        lambda: _lcts(plant, problem, results, (discount_rate, lifetime), on_error),
    )


def _lcts(plant, problem, results, discount, on_error):
    """Return the cost per joule of heat and cold; ``on_error`` applies to a missing value."""
    unit = f"{problem.assumptions.currency}/J"
    sited = problem.apply_site(plant)
    flows = Flows(sited, results)
    heat, cold = flows.energy("heat"), flows.energy("cold")
    if heat + cold <= 0:
        return unavailable(unit, "the run delivers neither heat nor cold", on_error)
    cost = annualised(sited, problem, results, discount, on_error)
    if cost["value"] is None:
        return unavailable(unit, cost["reason"], on_error)
    return value(
        cost["value"] / (heat + cold),
        unit,
        annualised_cost=value(cost["value"], cost["unit"]),
        heat=value(heat, "J/year"),
        cold=value(cold, "J/year"),
    )
