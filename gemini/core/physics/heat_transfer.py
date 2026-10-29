"""Pipe heat loss and standard heat-exchanger effectiveness relations."""

import math

from gemini.errors import PhysicsRangeError


def pipe_temperature_change(
    inlet_temperature: float,
    u_value: float,
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
    u_value, area : float
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
    Reference: GEMINI TemperatureDrop.calculate_dt; explicit steady energy balance
    UA*(T-T_ambient)/(m_dot*cp_mix). Zero-flow handling belongs to the path marcher.
    """
    total_mass_flow = liquid_mass_flow + gas_mass_flow
    if total_mass_flow == 0:
        raise PhysicsRangeError(
            f"pipe_temperature_change: total mass flow = {total_mass_flow} kg/s; expected a "
            "nonzero flow"
        )
    liquid_fraction = liquid_mass_flow / total_mass_flow
    gas_fraction = gas_mass_flow / total_mass_flow
    heat_capacity = liquid_fraction * liquid_heat_capacity + gas_fraction * gas_heat_capacity
    return (
        u_value
        * area
        * (inlet_temperature - ambient_temperature)
        / (total_mass_flow * heat_capacity)
    )


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
    _check_numbers("lmtd", dt1=dt1, dt2=dt2)
    if dt1 < 0 or dt2 < 0:
        raise PhysicsRangeError(
            f"lmtd: dt1 = {dt1} K, dt2 = {dt2} K; expected nonnegative terminal differences"
        )
    if dt1 == dt2:
        return dt1
    if dt1 == 0 or dt2 == 0:
        return 0.0
    return (dt1 - dt2) / math.log(dt1 / dt2)


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
    _check_numbers("ntu", ua=ua, c_min=c_min)
    if ua < 0 or c_min <= 0:
        raise PhysicsRangeError(
            f"ntu: ua = {ua} W/K, c_min = {c_min} W/K; expected ua >= 0 and c_min > 0"
        )
    return ua / c_min


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
    counterflow effectiveness–NTU relation, including the equal-capacity limit.
    """
    _check_effectiveness_inputs("effectiveness_counterflow", transfer_units, c_ratio)
    if c_ratio == 1:
        return 1.0 if math.isinf(transfer_units) else transfer_units / (1 + transfer_units)
    term = math.exp(-transfer_units * (1 - c_ratio))
    return (1 - term) / (1 - c_ratio * term)


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
    return -math.expm1(-transfer_units * (1 + c_ratio)) / (1 + c_ratio)


def _check_numbers(function, **values):
    """Reject NaN inputs, which would otherwise return NaN as if it were a valid result."""
    for name, value in values.items():
        if math.isnan(value):
            raise PhysicsRangeError(f"{function}: {name} = nan; expected a number")


def _check_effectiveness_inputs(function, transfer_units, c_ratio):
    """Require a nonnegative NTU and a capacity ratio in [0, 1]."""
    _check_numbers(function, transfer_units=transfer_units, c_ratio=c_ratio)
    if transfer_units < 0 or not 0 <= c_ratio <= 1:
        raise PhysicsRangeError(
            f"{function}: transfer_units = {transfer_units}, c_ratio = {c_ratio}; expected "
            "transfer_units >= 0 and c_ratio in [0, 1]"
        )
