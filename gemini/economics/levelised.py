"""Annualised system cost and the levelised cost of heat, of cold and of both."""

from gemini.economics.assumptions import discounting, resolve
from gemini.economics.costs import annual_energies, capex, opex
from gemini.economics.outcome import currency_of, reported, unavailable
from gemini.types.shapes import value


def annuity(rate, years):
    """Return the sum of ``1 / (1 + rate) ** t`` for the years ``t = 1 .. years``."""
    if rate == 0:
        return float(years)
    return (1 - (1 + rate) ** -years) / rate


def lifetime_cost(investment, yearly, factor):
    """Return the discounted cost of a lifetime: ``capex + opex * A``.

    Over ``A`` it is the annualised cost ``capex / A + opex``; ``lcoh`` and ``lcoc`` divide it by
    ``energy * A`` in one step, so their numbers stay those of that order of operations.
    """
    return investment + yearly * factor


def _levelised(plant, results, product, rate, years, assumptions, on_error):
    """Return the levelised cost of ``product`` ("heat" or "cold") over the lifetime."""
    return reported(
        on_error,
        f"{currency_of(assumptions)}/J",
        lambda: _cost_of(plant, results, product, rate, years, assumptions, on_error),
    )


def _cost_of(plant, results, product, rate, years, assumptions, on_error):
    """Compute the levelised cost; ``on_error`` applies to a value the plant cannot give."""
    assumptions = resolve(assumptions)
    rate, years = discounting(assumptions, rate, years)
    investment = capex(plant, assumptions, on_error)
    unit = f"{investment['unit']}/J"
    if investment["value"] is None:
        return unavailable(unit, investment["reason"], on_error)
    annual = annual_energies(plant, results)
    delivered, other = (
        (annual.heat, annual.cold) if product == "heat" else (annual.cold, annual.heat)
    )
    if delivered <= 0:
        return unavailable(unit, f"the run delivers no {product}", on_error)
    share = 1.0
    if other > 0:
        if assumptions.heat_cost_share is None:
            reason = "the plant delivers heat and cold; the split of its cost is not defined"
            return unavailable(unit, reason, on_error)
        heat_share = assumptions.heat_cost_share
        share = heat_share if product == "heat" else 1 - heat_share
    yearly = opex(plant, results, assumptions, "raise")["value"]
    factor = annuity(rate, years)
    cost = lifetime_cost(investment["value"], yearly, factor)
    return value(
        share * cost / (delivered * factor),
        unit,
        capex=value(investment["value"], investment["unit"]),
        opex=value(yearly, f"{investment['unit']}/year"),
        energy=value(delivered, "J/year"),
        discount_rate=value(rate, "-"),
        lifetime_years=value(years, "year"),
    )


def lcoh(plant, results, discount_rate=None, lifetime=None, assumptions=None, on_error="raise"):
    """Return the levelised cost of heat [currency/J]: the discounted cost over the discounted heat.

    ``(capex + opex * A) / (heat * A)`` with ``A`` the annuity factor, the sum over the lifetime
    years of ``1 / (1 + discount_rate) ** t``. ``capex`` and ``opex`` are the ``capex`` and
    ``opex`` of this package, ``opex`` and ``heat`` are per year as scaled from the run
    (``annual_energies``), constant over the lifetime, with no degradation, replacement or
    residual value. The whole plant cost is charged to the heat; for a plant that also delivers
    cold, ``assumptions.heat_cost_share`` of it, and without that share it gives no value.

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
    on_error : {"raise", "record"}, optional
        A value the inputs cannot give raises; ``"record"`` makes it ``None`` with a ``reason``.

    Returns
    -------
    dict
        ``{value, unit, capex, opex, energy, discount_rate, lifetime_years}``, the last five each
        a value; ``value`` in currency/J (multiply by 3.6e9 for currency/MWh). A plant that
        declares no cost, delivers no heat, or also delivers cold without a ``heat_cost_share`` has
        no value.
    """
    return _levelised(plant, results, "heat", discount_rate, lifetime, assumptions, on_error)


def lcoc(plant, results, discount_rate=None, lifetime=None, assumptions=None, on_error="raise"):
    """Return the levelised cost of cold [currency/J]; the cooling twin of ``lcoh``.

    The same formula with the cold delivered (what the water gains across the ``CoolingGrid``
    leaves) in place of the heat, and for a plant that also delivers heat the share of the cost
    ``heat_cost_share`` leaves. The parameters and the return shape are those of ``lcoh``.
    """
    return _levelised(plant, results, "cold", discount_rate, lifetime, assumptions, on_error)


def annualised_cost(
    plant, results, discount_rate=None, lifetime=None, assumptions=None, on_error="raise"
):
    """Return the annualised system cost [currency/year]: ``capex / A + opex``.

    ``A`` is the annuity factor of ``lcoh``, the sum over the lifetime years of
    ``1 / (1 + discount_rate) ** t``; ``capex`` and ``opex`` are those of this package, with the
    yearly cost as scaled from the run, constant over the lifetime.

    Parameters
    ----------
    plant, results : Module, Results
        A plant and its finished run.
    discount_rate : float, optional
        Real discount rate per year [-]; ``assumptions.discount_rate`` when ``None``.
    lifetime : int, optional
        Years of operation; ``assumptions.lifetime_years`` when ``None``.
    assumptions : Assumptions, optional
        Prices and, when not given above, the rate and lifetime.
    on_error : {"raise", "record"}, optional
        A value the inputs cannot give raises; ``"record"`` makes it ``None`` with a ``reason``.

    Returns
    -------
    dict
        ``{value, unit, capex, opex, annuity_factor, discount_rate, lifetime_years}``, the last
        five each a value. A plant that declares no cost has no value.
    """
    return reported(
        on_error,
        f"{currency_of(assumptions)}/year",
        lambda: _annualised(plant, results, discount_rate, lifetime, assumptions, on_error),
    )


def _annualised(plant, results, rate, years, assumptions, on_error):
    """Return the annualised cost; ``on_error`` applies to a plant without a cost."""
    assumptions = resolve(assumptions)
    rate, years = discounting(assumptions, rate, years)
    investment = capex(plant, assumptions, on_error)
    unit = f"{investment['unit']}/year"
    if investment["value"] is None:
        return unavailable(unit, investment["reason"], on_error)
    yearly = opex(plant, results, assumptions, "raise")["value"]
    factor = annuity(rate, years)
    return value(
        lifetime_cost(investment["value"], yearly, factor) / factor,
        unit,
        capex=value(investment["value"], investment["unit"]),
        opex=value(yearly, unit),
        annuity_factor=value(factor, "year"),
        discount_rate=value(rate, "-"),
        lifetime_years=value(years, "year"),
    )


def lcts(plant, results, discount_rate=None, lifetime=None, assumptions=None, on_error="raise"):
    """Return the levelised cost of thermal supply [currency/J].

    ``annualised_cost / (heat + cold)``, the heat and the cold delivered per year as scaled from
    the run (``annual_energies``). One cost over both products, so it needs no ``heat_cost_share``.
    The parameters are those of ``annualised_cost``.

    Returns
    -------
    dict
        ``{value, unit, annualised_cost, heat, cold}``, the last three each a value, ``heat`` and
        ``cold`` in J/year; ``value`` in currency/J (multiply by 3.6e9 for currency/MWh). A plant
        that declares no cost, or a run that delivers neither heat nor cold, has no value.
    """
    return reported(
        on_error,
        f"{currency_of(assumptions)}/J",
        lambda: _lcts(plant, results, discount_rate, lifetime, assumptions, on_error),
    )


def _lcts(plant, results, rate, years, assumptions, on_error):
    """Return the cost per joule of heat and cold; ``on_error`` applies to a missing value."""
    unit = f"{currency_of(assumptions)}/J"
    annual = annual_energies(plant, results)
    delivered = annual.heat + annual.cold
    if delivered <= 0:
        return unavailable(unit, "the run delivers neither heat nor cold", on_error)
    cost = annualised_cost(plant, results, rate, years, assumptions, on_error)
    if cost["value"] is None:
        return unavailable(unit, cost["reason"], on_error)
    return value(
        cost["value"] / delivered,
        unit,
        annualised_cost=value(cost["value"], cost["unit"]),
        heat=value(annual.heat, "J/year"),
        cold=value(annual.cold, "J/year"),
    )
