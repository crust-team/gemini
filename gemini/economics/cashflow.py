"""Net present value and payback of a plant run."""

from gemini.economics.assumptions import discounting, require, resolve
from gemini.economics.costs import annual_energies, capex, opex
from gemini.economics.levelised import annuity
from gemini.economics.outcome import currency_of, reported, unavailable
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
    investment = capex(plant, assumptions, "record")
    if investment["value"] is None:
        return None, None, investment["unit"], investment["reason"]
    yearly = opex(plant, results, assumptions, "raise")
    revenue = _revenue(assumptions, annual_energies(plant, results))
    return investment["value"], revenue - yearly["value"], investment["unit"], None


def npv(plant, results, discount_rate=None, lifetime=None, assumptions=None, on_error="raise"):
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
    on_error : {"raise", "record"}, optional
        A value the inputs cannot give raises; ``"record"`` makes it ``None`` with a ``reason``.

    Returns
    -------
    dict
        ``{value, unit, capex, net_cash_flow, discount_rate, lifetime_years}``, the last four each
        a value, with ``value`` and ``capex`` in the currency (``unit``) and ``net_cash_flow`` in
        currency per year. A plant that declares no cost has no value.
    """
    return reported(
        on_error,
        currency_of(assumptions),
        lambda: _npv(plant, results, discount_rate, lifetime, assumptions, on_error),
    )


def _npv(plant, results, discount_rate, lifetime, assumptions, on_error):
    """Return the net present value; ``on_error`` applies to a plant without a cost."""
    assumptions = resolve(assumptions)
    rate, years = discounting(assumptions, discount_rate, lifetime)
    investment, flow, unit, reason = _net_cash_flow(plant, results, assumptions)
    if investment is None:
        return unavailable(unit, reason, on_error)
    return value(
        flow * annuity(rate, years) - investment,
        unit,
        capex=value(investment, unit),
        net_cash_flow=value(flow, f"{unit}/year"),
        discount_rate=value(rate, "-"),
        lifetime_years=value(years, "year"),
    )


def payback(plant, results, assumptions=None, on_error="raise"):
    """Return the simple payback time [year]: ``capex / (revenue - opex)``, without discounting.

    Parameters
    ----------
    plant, results : Module, Results
        A plant and its finished run.
    assumptions : Assumptions, optional
        ``heat_price``, ``cold_price`` and the energy prices, as for ``npv``; anything needed and
        missing raises ``ValidationError`` (code ``missing_value``).
    on_error : {"raise", "record"}, optional
        A value the inputs cannot give raises; ``"record"`` makes it ``None`` with a ``reason``.

    Returns
    -------
    dict
        ``{value, unit, capex, net_cash_flow}`` with ``unit`` ``"year"`` and the last two each a
        value. A plant that declares no cost, or whose yearly revenue does not exceed its yearly
        cost (it never pays back), has no value.
    """
    return reported(on_error, "year", lambda: _payback(plant, results, assumptions, on_error))


def _payback(plant, results, assumptions, on_error):
    """Return the payback time; ``on_error`` applies to a value the plant cannot give."""
    assumptions = resolve(assumptions)
    investment, flow, unit, reason = _net_cash_flow(plant, results, assumptions)
    if investment is None:
        return unavailable("year", reason, on_error)
    details = dict(capex=value(investment, unit), net_cash_flow=value(flow, f"{unit}/year"))
    if flow <= 0:
        reason = "the yearly revenue does not exceed the yearly cost"
        return unavailable("year", reason, on_error, **details)
    return value(investment / flow, "year", **details)
