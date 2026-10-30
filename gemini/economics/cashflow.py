"""Net present value and payback of a plant run."""

from gemini.economics.assumptions import discounting, require, resolve
from gemini.economics.costs import annual_energies, capex, opex
from gemini.economics.levelised import annuity
from gemini.types.shapes import value


def _revenue(assumptions, annual):
    """Return the yearly revenue from the heat and cold sold; a needed price must be given."""
    revenue = 0.0
    if annual.heat > 0:
        revenue += annual.heat * require(assumptions, "heat_price")
    if annual.cold > 0:
        revenue += annual.cold * require(assumptions, "cold_price")
    return revenue


def _net_cash_flow(plant, results, assumptions):
    """Return ``(capex, yearly net cash flow, unit, reason)``; no cost gives ``None`` numbers."""
    investment = capex(plant, assumptions)
    if investment["value"] is None:
        return None, None, investment["unit"], investment["reason"]
    yearly = opex(plant, results, assumptions)
    revenue = _revenue(assumptions, annual_energies(plant, results))
    return investment["value"], revenue - yearly["value"], investment["unit"], None


def npv(plant, results, discount_rate=None, lifetime=None, assumptions=None):
    """Return the net present value [currency]: ``-capex + (revenue - opex) * A``.

    ``A`` is the annuity factor, the sum over the lifetime years of ``1 / (1 + rate) ** t``.
    The yearly revenue is the heat and cold delivered per year (``annual_energies``) at
    ``heat_price`` and ``cold_price``; the yearly cost is ``opex``. Both are constant over the
    lifetime, with no degradation, tax, replacement or residual value.

    Parameters
    ----------
    plant, results : Module, Results
        A plant and its finished run.
    discount_rate : float, optional
        Real discount rate per year [-]; ``assumptions.discount_rate`` when ``None``.
    lifetime : int, optional
        Years of operation; ``assumptions.lifetime_years`` when ``None``.
    assumptions : Assumptions, optional
        The prices, and the rate and lifetime when not given above. Anything needed and given
        nowhere raises ``ValidationError`` (code ``missing_value``).

    Returns
    -------
    dict
        ``{value, unit, capex, net_cash_flow, discount_rate, lifetime_years}``, the last four each
        a value, with ``value`` and ``capex`` in the currency (``unit``) and ``net_cash_flow`` in
        currency per year. ``value`` is ``None`` with a ``reason`` when the plant declares no cost.
    """
    assumptions = resolve(assumptions)
    rate, years = discounting(assumptions, discount_rate, lifetime)
    investment, flow, unit, reason = _net_cash_flow(plant, results, assumptions)
    if investment is None:
        return value(None, unit, reason)
    return value(
        flow * annuity(rate, years) - investment,
        unit,
        capex=value(investment, unit),
        net_cash_flow=value(flow, f"{unit}/year"),
        discount_rate=value(rate, "-"),
        lifetime_years=value(years, "year"),
    )


def payback(plant, results, assumptions=None):
    """Return the simple payback time [year]: ``capex / (revenue - opex)``, without discounting.

    Parameters
    ----------
    plant, results : Module, Results
        A plant and its finished run.
    assumptions : Assumptions, optional
        ``heat_price``, ``cold_price`` and the energy prices, as for ``npv``; anything needed and
        missing raises ``ValidationError`` (code ``missing_value``).

    Returns
    -------
    dict
        ``{value, unit, capex, net_cash_flow}`` with ``unit`` ``"year"`` and the last two each a
        value. ``value`` is ``None`` with a ``reason`` when the plant declares no cost or its
        yearly revenue does not exceed its yearly cost (it never pays back).
    """
    assumptions = resolve(assumptions)
    investment, flow, unit, reason = _net_cash_flow(plant, results, assumptions)
    if investment is None:
        return value(None, "year", reason)
    details = dict(capex=value(investment, unit), net_cash_flow=value(flow, f"{unit}/year"))
    if flow <= 0:
        reason = "the yearly revenue does not exceed the yearly cost"
        return value(None, "year", reason, **details)
    return value(investment / flow, "year", **details)
