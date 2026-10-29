"""Nodal analysis of geothermal wells: the flow or pressure at which well and reservoir agree.

A plant normally commands the production rate (``ProductionReservoir.production_rate``) and
reads the wellhead pressure that results. Nodal analysis inverts this: for a given wellhead
pressure it finds the rate at which the reservoir inflow and the well lift agree, and on the
injection side the rate or the wellhead pressure at which the injection well delivers the
bottomhole pressure the receiving aquifer needs. The functions are ported from the upstream
GEMINI simulator (``gemini_simulator.nodal_solver``), which solves the same balances with
``scipy.optimize.brentq``.

Every trial evaluates the plant's own modules (``ProductionReservoir.sandface_stream``,
``InjectionReservoir.required_pressure`` and ``Module.trial_outlets`` of the wells and the ESP),
so no running call records a trial. Call a solve before the plant call and apply its result
as a command, for example ``doublet.reservoir.production_rate = rate``. Each solve needs a
bracket whose two ends lie inside the well model's domain and give residuals of opposite sign:
very small rates can cool a stream below 0 K through the explicit heat loss and very large rates
can drive the traversed pressure below zero, and a trial there raises ``PhysicsRangeError``
naming the trial value.
"""

from pydantic import ValidationError
from scipy.optimize import brentq

from gemini.errors import ConfigurationError, PhysicsRangeError


def solve_production_rate(reservoir, well, wellhead_pressure, rates, esp=None, riser=None):
    """Return the production rate [kg/s] that delivers the wellhead pressure [Pa].

    Parameters
    ----------
    reservoir : ProductionReservoir
        Aquifer with its linear inflow performance.
    well : ProductionWell
        The full well, or with an ESP the segment below it (``segment="below_esp"``).
    wellhead_pressure : float
        Wellhead pressure [Pa] the surface plant holds.
    rates : tuple of float
        ``(low, high)`` mass flows [kg/s] bracketing the solution.
    esp, riser : ESP and ProductionWell, optional
        Pump and segment above it (``segment="above_esp"``), given together. The ESP runs at
        its persisted ``frequency``.

    Returns
    -------
    float
        The rate at which the sandface stream, lifted through well, ESP and riser, arrives at
        ``wellhead_pressure``. The wellhead pressure falls with rate (more drawdown and
        friction, less ESP head), so the root is unique within a valid bracket.

    Notes
    -----
    Upstream GEMINI walks the well downward from the wellhead and compares bottomhole
    pressures; this solve walks upward from the sandface as the plant does, so both sides of
    the balance use the same traversal as an ordinary plant call.
    """
    if (esp is None) != (riser is None):
        raise ConfigurationError(
            f"solve_production_rate: esp = {esp!r}, riser = {riser!r}; expected both or neither"
        )

    def residual(rate):
        stream = well.trial_outlets({"bottom": reservoir.sandface_stream(rate)}).wellhead
        if esp is not None:
            stream = esp.trial_outlets({"suction": stream}).discharge
            stream = riser.trial_outlets({"bottom": stream}).wellhead
        return stream.p - wellhead_pressure

    return _root("solve_production_rate", "rate", "kg/s", residual, rates)


def solve_injection_rate(well, sink, wellhead, rates):
    """Return the injection rate [kg/s] a wellhead stream's pressure pushes into the aquifer.

    Parameters
    ----------
    well : InjectionWell
        Injection well from wellhead to bottom.
    sink : InjectionReservoir
        Receiving aquifer with its linear injectivity.
    wellhead : Stream
        Wellhead temperature, pressure and fluid; its mass flow is replaced by trial rates.
    rates : tuple of float
        ``(low, high)`` mass flows [kg/s] bracketing the solution.

    Returns
    -------
    float
        The rate at which the well's bottom pressure equals ``sink.required_pressure``.
    """

    def residual(rate):
        return _injection_residual(well, sink, wellhead.with_(m_dot=rate))

    return _root("solve_injection_rate", "rate", "kg/s", residual, rates)


def solve_injection_pressure(well, sink, wellhead, pressures):
    """Return the wellhead pressure [Pa] that injects a stream, or ``None`` if none is needed.

    Parameters
    ----------
    well : InjectionWell
        Injection well from wellhead to bottom.
    sink : InjectionReservoir
        Receiving aquifer with its linear injectivity.
    wellhead : Stream
        Injected mass flow, temperature and fluid; its pressure is replaced by trial pressures.
    pressures : tuple of float
        ``(low, high)`` wellhead pressures [Pa]. Pass the pressure available without an
        injection pump, normally the pump suction, as ``low``.

    Returns
    -------
    float or None
        The wellhead pressure an injection pump must deliver. ``None`` means no pump is
        needed: already at ``low`` the column of brine delivers at least the bottomhole
        pressure the aquifer needs (common for deep injectors, which a choke throttles
        instead). Treat ``None`` as zero pump head and power, for example by commanding the
        pump to its suction pressure. Upstream GEMINI returned the bracket's lower end here.
    """

    def residual(pressure):
        return _injection_residual(well, sink, wellhead.with_(p=pressure))

    low = pressures[0]
    if _evaluate("solve_injection_pressure", "pressure", "Pa", residual, low) >= 0:
        return None
    return _root("solve_injection_pressure", "pressure", "Pa", residual, pressures)


def _injection_residual(well, sink, wellhead):
    """Return the injection well's bottom pressure minus the aquifer's required pressure [Pa]."""
    bottom = well.trial_outlets({"wellhead": wellhead}).bottom
    return bottom.p - sink.required_pressure(bottom)


def _root(function, name, unit, residual, bracket):
    """Return the root of ``residual`` in ``bracket`` after checking a sign change at its ends."""
    low, high = bracket
    at_low = _evaluate(function, name, unit, residual, low)
    at_high = _evaluate(function, name, unit, residual, high)
    if at_low * at_high > 0:
        raise PhysicsRangeError(
            f"{function}: residual = {at_low} Pa at {name} {low} {unit} and {at_high} Pa at "
            f"{high} {unit}; expected opposite signs (widen or move the bracket)"
        )
    return brentq(lambda value: _evaluate(function, name, unit, residual, value), low, high)


def _evaluate(function, name, unit, residual, value):
    """Return ``residual(value)``; a trial outside the well model's domain names the value."""
    try:
        return residual(value)
    except (PhysicsRangeError, ValidationError) as error:
        raise PhysicsRangeError(
            f"{function}: {name} = {value} {unit}; expected a trial inside the well model's "
            f"domain (narrow the bracket): {error}"
        ) from error
