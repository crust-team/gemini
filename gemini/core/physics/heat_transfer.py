"""Pipe heat loss and standard heat-exchanger effectiveness relations."""

import math


def pipe_temperature_change(
    t_in: float,
    u_value: float,
    area: float,
    m_l: float,
    m_g: float,
    cp_l: float,
    cp_g: float,
    t_ambient: float,
) -> float:
    """Return the legacy explicit heat-loss increment [K] using SI inputs.

    Parameters
    ----------
    t_in, t_ambient : float
        Fluid and ambient temperature [K].
    u_value, area : float
        Heat transfer coefficient [W/m2/K] and pipe surface area [m2].
    m_l, m_g : float
        Signed phase mass flows [kg/s].
    cp_l, cp_g : float
        Phase heat capacities [J/kg/K].

    Returns
    -------
    float
        Temperature increment [K]; the path marcher applies the direction sign.
    """
    mtot = m_l + m_g
    mlfrac = m_l / mtot
    mgfrac = m_g / mtot
    cp_mix = mlfrac * cp_l + mgfrac * cp_g
    return u_value * area * (t_in - t_ambient) / (mtot * cp_mix)


def lmtd(dt1: float, dt2: float) -> float:
    """Return logarithmic mean temperature difference [K]; reject a temperature cross."""
    if dt1 < 0 or dt2 < 0:
        raise ValueError("Terminal temperature differences must be nonnegative")
    if dt1 == dt2:
        return dt1
    if dt1 == 0 or dt2 == 0:
        return 0.0
    return (dt1 - dt2) / math.log(dt1 / dt2)


def ntu(ua: float, c_min: float) -> float:
    """Return number of transfer units [-] from UA [W/K] and capacity rate [W/K]."""
    if ua < 0 or c_min <= 0:
        raise ValueError("UA must be nonnegative and capacity rate positive")
    return ua / c_min


def effectiveness_counterflow(ntu: float, c_ratio: float) -> float:
    """Return counterflow effectiveness [-] from NTU [-] and capacity ratio [-]."""
    if ntu < 0 or not 0 <= c_ratio <= 1:
        raise ValueError("Require NTU >= 0 and capacity ratio in [0, 1]")
    if c_ratio == 1:
        return ntu / (1 + ntu)
    term = math.exp(-ntu * (1 - c_ratio))
    return (1 - term) / (1 - c_ratio * term)


def effectiveness_parallel(ntu: float, c_ratio: float) -> float:
    """Return parallel-flow effectiveness [-] from NTU [-] and capacity ratio [-]."""
    if ntu < 0 or not 0 <= c_ratio <= 1:
        raise ValueError("Require NTU >= 0 and capacity ratio in [0, 1]")
    return -math.expm1(-ntu * (1 + c_ratio)) / (1 + c_ratio)
