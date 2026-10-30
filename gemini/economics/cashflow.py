"""Net present value and payback of a plant run."""

from gemini.economics.assumptions import discounting, require, resolve
from gemini.economics.costs import annual_energies, capex, opex
from gemini.economics.levelised import annuity
from gemini.economics.outcome import outcome


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
        ``{value, unit, reason, capex, net_cash_flow, discount_rate, lifetime_years}`` with
        ``value`` and ``capex`` in the currency (``unit``) and ``net_cash_flow`` in currency per
        year. ``value`` is ``None`` with the ``reason`` when the plant declares no cost.
    """
    assumptions = resolve(assumptions)
    rate, years = discounting(assumptions, discount_rate, lifetime)
    investment, flow, unit, reason = _net_cash_flow(plant, results, assumptions)
    if investment is None:
        return outcome(None, unit, reason)
    return outcome(
        flow * annuity(rate, years) - investment,
        unit,
        None,
        capex=investment,
        net_cash_flow=flow,
        discount_rate=rate,
        lifetime_years=years,
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
        ``{value, unit, reason, capex, net_cash_flow}`` with ``unit`` ``"year"``. ``value`` is
        ``None`` with the ``reason`` when the plant declares no cost or its yearly revenue does
        not exceed its yearly cost (it never pays back).
    """
    assumptions = resolve(assumptions)
    investment, flow, _, reason = _net_cash_flow(plant, results, assumptions)
    if investment is None:
        return outcome(None, "year", reason)
    if flow <= 0:
        return outcome(
            None,
            "year",
            "the yearly revenue does not exceed the yearly cost",
            capex=investment,
            net_cash_flow=flow,
        )
    return outcome(investment / flow, "year", None, capex=investment, net_cash_flow=flow)
