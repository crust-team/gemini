"""Pipe heat loss and standard heat-exchanger effectiveness relations."""

from gemini import ops
from gemini.errors import PhysicsRangeError
from gemini.physics.fluid import FluidProperties

DEFAULT_CP = FluidProperties().cp_l
"""Liquid heat capacity [J/kg/K] assumed when measurements give none; the ``Fluid`` default."""

"""Fractional loss of the design conductance that raises the fouling alarm [-]; a GEMINI
alarm convention without a published source."""

DUTY_AGREEMENT_TOLERANCE = 0.05
"""Largest relative difference [-] of the hot and cold duties for which an apparent UA is taken."""

DETERMINED, NONPOSITIVE_INPUT, DISAGREEING_DUTIES, NO_LMTD = 0, 1, 2, 3
"""Codes of ``apparent_conductance``: determined, or the first reason that it is not."""


@ops.physics
def pipe_temperature_change(
    inlet_temperature: float,
    heat_transfer_coefficient: float,
    area: float,
    liquid_mass_flow: float,
    gas_mass_flow: float,
    liquid_heat_capacity: float,
    gas_heat_capacity: float,
    ambient_temperature: float,
) -> float:
    """Return the legacy explicit heat-loss increment [K] using SI inputs.

    Parameters
    ----------
    inlet_temperature, ambient_temperature : float
        Fluid and ambient temperature [K].
    heat_transfer_coefficient, area : float
        Heat transfer coefficient [W/m2/K] and pipe surface area [m2].
    liquid_mass_flow, gas_mass_flow : float
        Signed phase mass flows [kg/s] with a nonzero sum.
    liquid_heat_capacity, gas_heat_capacity : float
        Phase heat capacities [J/kg/K].

    Returns
    -------
    float
        Temperature increment [K]; the path marcher applies the direction sign.

    Notes
    -----
    Reference: GEMINI TemperatureDrop.calculate_dt, a retained formulation of the steady
    energy balance of a pipe stream, UA*(T-T_ambient)/(m_dot*cp_mix), explicit in the inlet
    temperature (Incropera et al., Fundamentals of Heat and Mass Transfer, internal flow
    energy balance). Zero-flow handling belongs to the path marcher.
    """
    total_mass_flow = liquid_mass_flow + gas_mass_flow
    ops.check(
        total_mass_flow != 0,
        PhysicsRangeError,
        "pipe_temperature_change: total mass flow = {total_mass_flow} kg/s; expected a "
        "nonzero flow",
        total_mass_flow=total_mass_flow,
    )
    liquid_fraction = liquid_mass_flow / total_mass_flow
    gas_fraction = gas_mass_flow / total_mass_flow
    heat_capacity = liquid_fraction * liquid_heat_capacity + gas_fraction * gas_heat_capacity
    return (
        heat_transfer_coefficient
        * area
        * (inlet_temperature - ambient_temperature)
        / (total_mass_flow * heat_capacity)
    )


@ops.physics
def lmtd(dt1: float, dt2: float) -> float:
    """Return logarithmic mean temperature difference; reject a temperature cross.

    Parameters
    ----------
    dt1, dt2 : float
        Nonnegative terminal temperature differences [K].

    Returns
    -------
    float
        Logarithmic mean temperature difference [K]; zero at a pinched terminal.

    Notes
    -----
    Reference: Incropera et al., Fundamentals of Heat and Mass Transfer,
    heat-exchanger LMTD method: (dt1-dt2)/ln(dt1/dt2).
    """
    ops.check_numbers("lmtd", dt1=dt1, dt2=dt2)
    ops.check(
        ops.logical_and(dt1 >= 0, dt2 >= 0),
        PhysicsRangeError,
        "lmtd: dt1 = {dt1} K, dt2 = {dt2} K; expected nonnegative terminal differences",
        dt1=dt1,
        dt2=dt2,
    )
    logarithmic = logarithmic_mean(dt1, dt2)
    return ops.where(
        dt1 == dt2, dt1, ops.where(ops.logical_or(dt1 == 0, dt2 == 0), 0.0, logarithmic)
    )


@ops.physics
def ntu(ua: float, c_min: float) -> float:
    """Return the number of transfer units.

    Parameters
    ----------
    ua, c_min : float
        Nonnegative conductance [W/K] and positive minimum capacity rate [W/K].

    Returns
    -------
    float
        NTU = UA/C_min [-].

    Notes
    -----
    Reference: Incropera et al., Fundamentals of Heat and Mass Transfer,
    effectiveness–NTU method.
    """
    ops.check_numbers("ntu", ua=ua, c_min=c_min)
    ops.check(
        ops.logical_and(ua >= 0, c_min > 0),
        PhysicsRangeError,
        "ntu: ua = {ua} W/K, c_min = {c_min} W/K; expected ua >= 0 and c_min > 0",
        ua=ua,
        c_min=c_min,
    )
    return ua / c_min


@ops.physics
def effectiveness_counterflow(transfer_units: float, c_ratio: float) -> float:
    """Return counterflow heat-exchanger effectiveness.

    Parameters
    ----------
    transfer_units, c_ratio : float
        Nonnegative number of transfer units NTU [-] and C_min/C_max in [0, 1] [-].

    Returns
    -------
    float
        Heat transferred divided by the maximum possible heat [-].

    Notes
    -----
    Reference: Incropera et al., Fundamentals of Heat and Mass Transfer,
    counterflow effectiveness–NTU relation, including the equal-capacity limit:
    e = (1-exp(-NTU(1-Cr)))/(1-Cr exp(-NTU(1-Cr))), and NTU/(1+NTU) at Cr = 1.
    """
    _check_effectiveness_inputs("effectiveness_counterflow", transfer_units, c_ratio)
    balanced = ops.where(ops.isinf(transfer_units), 1.0, transfer_units / (1 + transfer_units))
    term = ops.exp(-transfer_units * (1 - c_ratio))
    return ops.where(c_ratio == 1, balanced, (1 - term) / (1 - c_ratio * term))


@ops.physics
def effectiveness_parallel(transfer_units: float, c_ratio: float) -> float:
    """Return parallel-flow heat-exchanger effectiveness.

    Parameters
    ----------
    transfer_units, c_ratio : float
        Nonnegative number of transfer units NTU [-] and C_min/C_max in [0, 1] [-].

    Returns
    -------
    float
        Heat transferred divided by the maximum possible heat [-].

    Notes
    -----
    Reference: Incropera et al., Fundamentals of Heat and Mass Transfer,
    parallel-flow relation: (1-exp(-NTU*(1+Cr)))/(1+Cr).
    """
    _check_effectiveness_inputs("effectiveness_parallel", transfer_units, c_ratio)
    return -ops.expm1(-transfer_units * (1 + c_ratio)) / (1 + c_ratio)


def _check_effectiveness_inputs(function, transfer_units, c_ratio):
    """Require a nonnegative NTU and a capacity ratio in [0, 1]."""
    ops.check_numbers(function, transfer_units=transfer_units, c_ratio=c_ratio)
    ops.check(
        ops.logical_and(transfer_units >= 0, ops.logical_and(c_ratio >= 0, c_ratio <= 1)),
        PhysicsRangeError,
        "{function}: transfer_units = {transfer_units}, c_ratio = {c_ratio}; expected "
        "transfer_units >= 0 and c_ratio in [0, 1]",
        function=function,
        transfer_units=transfer_units,
        c_ratio=c_ratio,
    )


@ops.physics
def logarithmic_mean(first: float, second: float) -> float:
    """Return the logarithmic mean of two positive values, without guards.

    Parameters
    ----------
    first, second : float
        Positive values of the same unit, for example temperatures or temperature differences
        [K]; they must differ, since the equal case is a ``0/0``.

    Returns
    -------
    float
        ``(first - second) / ln(first / second)`` in the unit of the inputs.

    Notes
    -----
    Reference: Incropera et al., Fundamentals of Heat and Mass Transfer, LMTD method; Lorenz
    (1894) for the mean temperature of a glide. The callers ``lmtd`` and
    ``refrigeration.log_mean_temperature`` guard the equal and the pinched case.
    """
    return (first - second) / ops.log(first / second)


@ops.physics
def signed_parts(value):
    """Return the positive part and the negative part of a signed value.

    Parameters
    ----------
    value : float
        Signed quantity in any unit, for example a heat rate [W] positive when absorbed.

    Returns
    -------
    tuple of float
        ``(max(value, 0), max(-value, 0))`` in the unit of ``value``; both are nonnegative and
        at most one is nonzero.

    Notes
    -----
    Pure bookkeeping split of a signed flow into the two directions; valid for any real value.

    Source: A plain definition of the positive and negative part, no published source.
    """
    return ops.maximum(value, 0), ops.maximum(-value, 0)


@ops.physics
def heat_rate(capacity_rate: float, temperature_difference: float) -> float:
    """Return the sensible heat rate of a stream.

    Parameters
    ----------
    capacity_rate : float
        Heat capacity rate ``m cp`` [W/K].
    temperature_difference : float
        Temperature change or difference [K], with the sign of the wanted heat direction.

    Returns
    -------
    float
        ``Q = C dT`` [W].

    Notes
    -----
    Reference: Incropera et al., Fundamentals of Heat and Mass Transfer, steady-flow energy
    balance of a single-phase stream with constant heat capacity.

    Validity: capacity_rate nonnegative, temperature_difference real; no division occurs. Single
    phase with a constant heat capacity.
    """
    return capacity_rate * temperature_difference


@ops.physics
def setpoint_duty(capacity_rate: float, temperature_gap: float) -> float:
    """Return the heat needed to close a temperature gap; zero when there is no gap.

    Parameters
    ----------
    capacity_rate : float
        Heat capacity rate ``m cp`` [W/K].
    temperature_gap : float
        Setpoint minus inlet temperature [K]; negative when the stream is already beyond it.

    Returns
    -------
    float
        ``Q = C max(0, gap)`` [W], nonnegative.

    Notes
    -----
    Reference: Incropera et al., Fundamentals of Heat and Mass Transfer, steady-flow energy
    balance, limited to the heating direction of an ideal heater to a setpoint.
    """
    return capacity_rate * ops.maximum(0, temperature_gap)


@ops.physics
def temperature_change(duty: float, capacity_rate: float) -> float:
    """Return the temperature change of a stream that receives a duty; zero when stopped.

    Parameters
    ----------
    duty : float
        Heat added to the stream [W], negative when removed.
    capacity_rate : float
        Heat capacity rate ``m cp`` [W/K], nonnegative.

    Returns
    -------
    float
        ``dT = Q / C`` [K]; zero when the capacity rate is zero.

    Notes
    -----
    Reference: Incropera et al., Fundamentals of Heat and Mass Transfer, steady-flow energy
    balance. A stopped stream has no meaningful change, and zero is returned for it.
    """
    return ops.where(capacity_rate == 0, 0.0, duty / capacity_rate)


@ops.physics
def effectiveness_outlet_temperature(
    inlet_temperature: float, effectiveness: float, reference_temperature: float
) -> float:
    """Return the outlet temperature of a stream from the effectiveness definition.

    Parameters
    ----------
    inlet_temperature : float
        Stream inlet temperature [K].
    effectiveness : float
        Heat transferred divided by the maximum possible heat [-], in [0, 1].
    reference_temperature : float
        Temperature [K] that the stream would reach with infinite transfer area: the other
        stream inlet or the constant ambient temperature.

    Returns
    -------
    float
        ``T_out = T_in - e (T_in - T_ref)`` [K].

    Notes
    -----
    Reference: Incropera et al., Fundamentals of Heat and Mass Transfer, effectiveness-NTU
    method, definition of the effectiveness.
    """
    return inlet_temperature - effectiveness * (inlet_temperature - reference_temperature)


@ops.physics
def ambient_effectiveness(conductance: float, capacity_rate: float) -> float:
    """Return the effectiveness of a stream exchanging heat with a constant temperature.

    Parameters
    ----------
    conductance : float
        Nonnegative overall conductance ``UA`` between the stream and its surroundings [W/K].
    capacity_rate : float
        Heat capacity rate ``m cp`` of the stream [W/K], nonnegative.

    Returns
    -------
    float
        ``e = 1 - exp(-UA / C)`` [-]; zero for a stopped stream (``C = 0``).

    Notes
    -----
    Reference: Incropera et al., Fundamentals of Heat and Mass Transfer, effectiveness-NTU
    relation for ``C_r = 0`` (a phase change or a very large capacity on the other side), valid
    for a pipe, coil or borehole at a constant wall or ground temperature. It is the
    ``effectiveness_parallel`` relation at zero capacity ratio.
    """
    return ops.where(
        capacity_rate == 0, 0.0, effectiveness_parallel(ntu(conductance, capacity_rate), 0.0)
    )


@ops.physics
def relaxation_factor(conductance: float, duration: float, heat_capacity: float) -> float:
    """Return the decay factor of a lumped body relaxing towards its surroundings.

    Parameters
    ----------
    conductance : float
        Nonnegative conductance to the surroundings [W/K].
    duration : float
        Time step [s], nonnegative.
    heat_capacity : float
        Positive thermal capacity of the body [J/K].

    Returns
    -------
    float
        ``f = exp(-UA dt / C)`` [-] in (0, 1].

    Notes
    -----
    Reference: Incropera et al., Fundamentals of Heat and Mass Transfer, lumped capacitance
    method: ``(T - T_eq) = (T_0 - T_eq) exp(-t / tau)`` with ``tau = C / UA``.
    """
    return ops.exp(-conductance * duration / heat_capacity)


@ops.physics
def exponential_relaxation(start: float, equilibrium: float, factor: float) -> float:
    """Return the value after an exponential approach to an equilibrium.

    Parameters
    ----------
    start, equilibrium : float
        Initial and equilibrium value, in the same unit (for example [K]).
    factor : float
        Remaining fraction [-] from ``relaxation_factor``.

    Returns
    -------
    float
        ``x = x_eq + (x_0 - x_eq) f``, in the unit of ``start``.

    Notes
    -----
    Reference: Incropera et al., Fundamentals of Heat and Mass Transfer, lumped capacitance
    method with a constant equilibrium temperature over the step.

    Validity: start and equilibrium real in one unit; factor in [0, 1] (the output of
    ``relaxation_factor``); no division occurs.
    """
    return equilibrium + (start - equilibrium) * factor


@ops.physics
def mixed_temperature(
    first_rate: float, first_temperature: float, second_rate: float, second_temperature: float
) -> float:
    """Return the adiabatic mixing temperature of two streams of the same fluid.

    Parameters
    ----------
    first_rate, second_rate : float
        Heat capacity rates ``m cp`` [W/K], nonnegative.
    first_temperature, second_temperature : float
        Stream temperatures [K].

    Returns
    -------
    float
        ``T = (C1 T1 + C2 T2) / (C1 + C2)`` [K]; the plain mean of the two temperatures when
        both streams are stopped.

    Notes
    -----
    Reference: Moran and Shapiro, Fundamentals of Engineering Thermodynamics, adiabatic mixing
    of streams with constant heat capacity.
    """
    total_rate = first_rate + second_rate
    return ops.where(
        total_rate == 0,
        (first_temperature + second_temperature) / 2,
        (first_rate * first_temperature + second_rate * second_temperature) / total_rate,
    )


@ops.physics
def sensible_latent_loads(
    available: float, sensible_demand: float, latent_demand: float, is_dry: bool
) -> tuple:
    """Return the sensible and latent loads a cooling circuit takes up, sensible served first.

    Parameters
    ----------
    available : float
        Heat the circuit can absorb [W], nonnegative.
    sensible_demand, latent_demand : float
        Sensible and latent cooling demands [W], nonnegative.
    is_dry : bool
        True when the coil is above the dew point, so nothing condenses.

    Returns
    -------
    tuple of float
        ``(min(S, A), min(L, A - Q_s))`` [W], with the latent load zero when ``is_dry``.

    Notes
    -----
    Retained GEMINI priority: thermostats control the dry-bulb temperature and humidity drifts
    when capacity is short (ASHRAE Handbook, HVAC Systems and Equipment, chapter 23).
    """
    sensible = ops.minimum(sensible_demand, available)
    latent = ops.minimum(latent_demand, available - sensible)
    return sensible, ops.where(is_dry, 0.0, latent)


@ops.physics
def fan_power(duty: float, specific_fan_power: float) -> float:
    """Return the fan electricity of a cooler that is proportional to its duty.

    Parameters
    ----------
    duty : float
        Heat rejected [W].
    specific_fan_power : float
        Fan electricity per unit of rejected heat [-].

    Returns
    -------
    float
        ``P = specific_fan_power * Q`` [W].

    Notes
    -----
    Speed-controlled fans without the cubic fan law: a retained GEMINI simplification (ASHRAE
    Handbook, HVAC Systems and Equipment, chapters on cooling towers and dry coolers, give the
    fan power of a cooler as a fraction of its capacity).

    Validity: duty and specific_fan_power nonnegative; no division occurs. A fan power proportional
    to the duty is a simplification, not a fan law.
    """
    return specific_fan_power * duty


@ops.physics
def mean_temperature(first: float, second: float) -> float:
    """Return the arithmetic mean of two temperatures.

    Parameters
    ----------
    first, second : float
        Temperatures [K], for example the inlet and the outlet of a stream.

    Returns
    -------
    float
        ``(first + second) / 2`` [K].

    Notes
    -----
    Mean circuit temperature of a characteristic-equation machine (Hellmann, Schweigler and
    Ziegler 1999).

    Validity: Valid for any two real temperatures, positive [K] in practice; no division occurs.
    """
    return (first + second) / 2


@ops.physics
def exchanger_balance(
    hot_inlet: float,
    cold_inlet: float,
    hot_rate: float,
    cold_rate: float,
    conductance: float,
    counterflow: bool,
) -> tuple:
    """Return the effectiveness-NTU balance of a two-stream heat exchanger.

    Parameters
    ----------
    hot_inlet, cold_inlet : float
        Inlet temperatures [K] of the hot and the cold stream.
    hot_rate, cold_rate : float
        Heat capacity rates ``m cp`` [W/K], nonnegative.
    conductance : float
        Overall conductance UA [W/K], nonnegative.
    counterflow : bool
        True for counterflow, false for parallel flow (a static choice of the arrangement).

    Returns
    -------
    tuple of float
        ``(effectiveness, NTU, duty, hot outlet, cold outlet)`` [-, -, W, K, K]:
        ``NTU = UA / C_min``, ``Q = eps C_min (T_hot - T_cold)``, ``T_hot,out = T_hot - Q /
        C_hot`` and ``T_cold,out = T_cold + Q / C_cold``. A stopped stream (``C_min = 0``)
        transfers no heat: all of effectiveness, NTU and duty are zero and the outlets equal the
        inlets.

    Notes
    -----
    Reference: Incropera et al., Fundamentals of Heat and Mass Transfer, effectiveness-NTU
    method, with ``effectiveness_counterflow`` or ``effectiveness_parallel``. Read the result
    by index when the check on a negative conductance can fail.
    """
    c_min, c_max = ops.minimum(hot_rate, cold_rate), ops.maximum(hot_rate, cold_rate)
    stopped = c_min == 0
    transfer_units = ntu(conductance, c_min)
    method = effectiveness_counterflow if counterflow else effectiveness_parallel
    effectiveness = method(transfer_units, c_min / c_max)
    duty = effectiveness * c_min * (hot_inlet - cold_inlet)
    hot_outlet = hot_inlet - duty / hot_rate
    cold_outlet = cold_inlet + duty / cold_rate
    return (
        ops.where(stopped, 0.0, effectiveness),
        ops.where(stopped, 0.0, transfer_units),
        ops.where(stopped, 0.0, duty),
        ops.where(stopped, hot_inlet, hot_outlet),
        ops.where(stopped, cold_inlet, cold_outlet),
    )


@ops.physics
def terminal_differences(
    hot_in: float, hot_out: float, cold_in: float, cold_out: float, counterflow: bool
) -> tuple:
    """Return the two terminal temperature differences of a two-stream exchanger.

    Parameters
    ----------
    hot_in, hot_out, cold_in, cold_out : float
        Inlet and outlet temperatures [K] of the hot and the cold stream.
    counterflow : bool
        True for counterflow, false for parallel flow (a static choice of the arrangement).

    Returns
    -------
    tuple of float
        ``(dt1, dt2)`` [K]: ``(hot_in - cold_out, hot_out - cold_in)`` for counterflow and
        ``(hot_in - cold_in, hot_out - cold_out)`` for parallel flow.

    Notes
    -----
    Reference: Incropera et al., Fundamentals of Heat and Mass Transfer, LMTD method; the
    differences feed ``lmtd``.
    """
    if counterflow:
        return hot_in - cold_out, hot_out - cold_in
    return hot_in - cold_in, hot_out - cold_out


@ops.physics
def apparent_conductance(
    arrangement,
    hot_in_T,
    hot_out_T,
    cold_in_T,
    cold_out_T,
    m_dot_hot,
    m_dot_cold,
    cp_hot,
    cp_cold,
):
    """Return ``(UA, code, hot duty, cold duty, LMTD)`` from measured temperatures and flows.

    Parameters
    ----------
    arrangement : str
        ``"counterflow"``, otherwise parallel flow (a static choice).
    hot_in_T, hot_out_T, cold_in_T, cold_out_T : float
        Inlet and outlet temperatures [K] of the hot and the cold stream.
    m_dot_hot, m_dot_cold : float
        Mass flows [kg/s].
    cp_hot, cp_cold : float
        Heat capacities [J/kg/K].

    Returns
    -------
    tuple
        ``(UA, code, Q_hot, Q_cold, LMTD)``: apparent conductance [W/K], status code, duties
        [W] and logarithmic mean temperature difference [K]. ``code`` is ``DETERMINED`` when
        the measurements fix an apparent UA, else the first reason that they do not:
        ``NONPOSITIVE_INPUT`` for a nonpositive flow or capacity, ``DISAGREEING_DUTIES`` for
        duties that differ by more than ``DUTY_AGREEMENT_TOLERANCE``, ``NO_LMTD`` for no
        positive LMTD.

    Notes
    -----
    ``UA = (Q_hot + Q_cold) / 2 / LMTD``, the LMTD method of Incropera et al., Fundamentals of
    Heat and Mass Transfer, applied to measurements. A row that is already undetermined gives
    LMTD zero terminal differences, so an invalid temperature of such a row raises nothing, as
    it does not when one row is evaluated alone. Read the result by index.

    Source: Incropera et al., Fundamentals of Heat and Mass Transfer, LMTD method, applied to
    measurements.
    """
    smallest = ops.minimum(ops.minimum(ops.minimum(m_dot_hot, m_dot_cold), cp_hot), cp_cold)
    qh = heat_rate(m_dot_hot * cp_hot, hot_in_T - hot_out_T)
    qc = heat_rate(m_dot_cold * cp_cold, cold_out_T - cold_in_T)
    disagree = ops.logical_or(
        ops.minimum(qh, qc) <= 0,
        ops.abs(qh - qc) / ops.maximum(qh, qc) > DUTY_AGREEMENT_TOLERANCE,
    )
    dt1, dt2 = terminal_differences(
        hot_in_T, hot_out_T, cold_in_T, cold_out_T, arrangement == "counterflow"
    )
    determined = ops.logical_not(ops.logical_or(smallest <= 0, disagree))
    delta = lmtd(ops.where(determined, dt1, 0.0), ops.where(determined, dt2, 0.0))
    code = ops.where(
        smallest <= 0,
        NONPOSITIVE_INPUT,
        ops.where(disagree, DISAGREEING_DUTIES, ops.where(delta <= 0, NO_LMTD, DETERMINED)),
    )
    return (qh + qc) / 2 / delta, code, qh, qc, delta
