"""Levelised cost of heat and of cold."""

from gemini.economics.assumptions import discounting, resolve
from gemini.economics.costs import annual_energies, capex, opex
from gemini.types.shapes import value


def annuity(rate, years):
    """Return the sum of ``1 / (1 + rate) ** t`` for the years ``t = 1 .. years``."""
    if rate == 0:
        return float(years)
    return (1 - (1 + rate) ** -years) / rate


def _levelised(plant, results, product, rate, years, assumptions):
    """Return the levelised cost of ``product`` ("heat" or "cold") over the lifetime."""
    assumptions = resolve(assumptions)
    rate, years = discounting(assumptions, rate, years)
    investment = capex(plant, assumptions)
    unit = f"{investment['unit']}/J"
    if investment["value"] is None:
        return value(None, unit, investment["reason"])
    annual = annual_energies(plant, results)
    delivered, other = (
        (annual.heat, annual.cold) if product == "heat" else (annual.cold, annual.heat)
    )
    if delivered <= 0:
        return value(None, unit, f"the run delivers no {product}")
    if other > 0:
        return value(
            None, unit, "the plant delivers heat and cold; the split of its cost is not defined"
        )
    yearly = opex(plant, results, assumptions)["value"]
    factor = annuity(rate, years)
    cost = investment["value"] + yearly * factor
    return value(
        cost / (delivered * factor),
        unit,
        capex=value(investment["value"], investment["unit"]),
        opex=value(yearly, f"{investment['unit']}/year"),
        energy=value(delivered, "J/year"),
        discount_rate=value(rate, "-"),
        lifetime_years=value(years, "year"),
    )


def lcoh(plant, results, discount_rate=None, lifetime=None, assumptions=None):
    """Return the levelised cost of heat [currency/J]: the discounted cost over the discounted heat.

    ``(capex + opex * A) / (heat * A)`` with ``A`` the annuity factor, the sum over the lifetime
    years of ``1 / (1 + discount_rate) ** t``. ``capex`` and ``opex`` are the ``capex`` and
    ``opex`` of this package, ``opex`` and ``heat`` are per year as scaled from the run
    (``annual_energies``), constant over the lifetime, with no degradation, replacement or
    residual value. The whole plant cost is charged to the heat, so a plant that also delivers
    cold gives no value.

    Parameters
    ----------
    plant, results : Module, Results
        A plant and its finished run.
    discount_rate : float, optional
        Real discount rate per year [-]; ``assumptions.discount_rate`` when ``None``.
    lifetime : int, optional
        Years of operation; ``assumptions.lifetime_years`` when ``None``.
    assumptions : Assumptions, optional
        Prices and, when not given above, the rate and lifetime. A rate or lifetime given nowhere
        raises ``ValidationError`` (code ``missing_value``).

    Returns
    -------
    dict
        ``{value, unit, capex, opex, energy, discount_rate, lifetime_years}``, the last five each
        a value; ``value`` in currency/J (multiply by 3.6e9 for currency/MWh), ``None`` with a
        ``reason`` when the plant declares no cost, delivers no heat or also delivers cold.
    """
    return _levelised(plant, results, "heat", discount_rate, lifetime, assumptions)


def lcoc(plant, results, discount_rate=None, lifetime=None, assumptions=None):
    """Return the levelised cost of cold [currency/J]; the cooling twin of ``lcoh``.

    The same formula with the cold delivered (``heat_absorbed`` of the ``CoolingConsumer``
    leaves) in place of the heat, and a plant that also delivers heat gives no value. The
    parameters and the return shape are those of ``lcoh``.
    """
    return _levelised(plant, results, "cold", discount_rate, lifetime, assumptions)
