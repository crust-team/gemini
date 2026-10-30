"""Ideal-gas adiabatic compression with an isentropic efficiency and intercooled stages.

The relations are the textbook ideal-gas forms used for compressor sizing, for example GPSA
Engineering Data Book, 14th ed. (2017), Section 13 "Compressors and Expanders", with the
compressibility factor Z = 1: the isentropic outlet temperature
``T_2s = T_1 * r**((k - 1) / k)`` and the actual adiabatic outlet temperature
``T_2 = T_1 + (T_2s - T_1) / eta_s``. They hold for gases near ideal behaviour (Z close to one,
low reduced pressure) with a constant heat capacity ratio ``k = cp / cv`` over the stage.
"""

from gemini import ops
from gemini.errors import PhysicsRangeError


def isentropic_outlet_temperature(
    inlet_temperature: float, pressure_ratio: float, heat_capacity_ratio: float
) -> float:
    """Return the ideal-gas isentropic outlet temperature [K] of one compression stage.

    Parameters
    ----------
    inlet_temperature : float
        Suction temperature [K], positive.
    pressure_ratio : float
        Discharge over suction absolute pressure [-], at least one.
    heat_capacity_ratio : float
        Constant ``k = cp / cv`` [-], greater than one.

    Returns
    -------
    float
        ``T_2s = T_1 * r**((k - 1) / k)`` [K].

    Notes
    -----
    Reference: GPSA Engineering Data Book, 14th ed. (2017), Section 13, isentropic compression
    of an ideal gas (Z = 1, constant k).
    """
    _check_stage("isentropic_outlet_temperature", inlet_temperature, pressure_ratio)
    ops.check(
        heat_capacity_ratio > 1,
        PhysicsRangeError,
        "isentropic_outlet_temperature: heat_capacity_ratio = {heat_capacity_ratio}; expected > 1",
        heat_capacity_ratio=heat_capacity_ratio,
    )
    return inlet_temperature * ops.pow(
        pressure_ratio, (heat_capacity_ratio - 1) / heat_capacity_ratio
    )


def stage_outlet_temperature(
    inlet_temperature: float,
    pressure_ratio: float,
    heat_capacity_ratio: float,
    isentropic_efficiency: float,
) -> float:
    """Return the adiabatic outlet temperature [K] of one stage with an isentropic efficiency.

    Parameters
    ----------
    inlet_temperature, pressure_ratio, heat_capacity_ratio : float
        As in ``isentropic_outlet_temperature``.
    isentropic_efficiency : float
        Isentropic (adiabatic) stage efficiency [-] in (0, 1].

    Returns
    -------
    float
        ``T_2 = T_1 + (T_2s - T_1) / eta_s`` [K]: every loss of an adiabatic stage heats the gas.

    Notes
    -----
    Reference: GPSA Engineering Data Book, 14th ed. (2017), Section 13, actual discharge
    temperature from the isentropic efficiency.
    """
    ops.check(
        ops.logical_and(isentropic_efficiency > 0, isentropic_efficiency <= 1),
        PhysicsRangeError,
        "stage_outlet_temperature: isentropic_efficiency = {isentropic_efficiency}; "
        "expected in (0, 1]",
        isentropic_efficiency=isentropic_efficiency,
    )
    ideal = isentropic_outlet_temperature(inlet_temperature, pressure_ratio, heat_capacity_ratio)
    return inlet_temperature + ops.truediv(ideal - inlet_temperature, isentropic_efficiency)


def specific_compression_work(
    inlet_temperature: float,
    pressure_ratio: float,
    heat_capacity_ratio: float,
    specific_heat: float,
    isentropic_efficiency: float,
    stages: int,
) -> float:
    """Return the shaft work per kg of gas [J/kg] of an intercooled multistage compressor.

    Parameters
    ----------
    inlet_temperature, pressure_ratio, heat_capacity_ratio, isentropic_efficiency : float
        As in ``stage_outlet_temperature``; ``pressure_ratio`` is the overall ratio.
    specific_heat : float
        Constant gas heat capacity at constant pressure ``cp`` [J/kg/K], positive.
    stages : int
        Number of equal stages, at least one.

    Returns
    -------
    float
        ``w = N * cp * (T_2 - T_1)`` [J/kg] with the stage ratio ``r**(1 / N)``.

    Notes
    -----
    Every stage has the same pressure ratio and isentropic efficiency, and the intercoolers
    return the gas to the suction temperature before each later stage. This equal split
    minimises the work of an ideal intercooled compressor (GPSA Engineering Data Book, 14th ed.
    (2017), Section 13, multistage compression).
    """
    ops.check(
        ops.logical_and(specific_heat > 0, stages >= 1),
        PhysicsRangeError,
        "specific_compression_work: specific_heat = {specific_heat} J/kg/K, stages = "
        "{stages}; expected a positive heat capacity and at least one stage",
        specific_heat=specific_heat,
        stages=stages,
    )
    _check_stage("specific_compression_work", inlet_temperature, pressure_ratio)
    outlet = stage_outlet_temperature(
        inlet_temperature,
        ops.pow(pressure_ratio, ops.truediv(1, stages)),
        heat_capacity_ratio,
        isentropic_efficiency,
    )
    return stages * specific_heat * (outlet - inlet_temperature)


def _check_stage(name, inlet_temperature, pressure_ratio):
    """Reject a nonpositive or non-finite temperature and a pressure ratio below one."""
    ops.check(
        ops.logical_and(ops.isfinite(inlet_temperature), inlet_temperature > 0),
        PhysicsRangeError,
        "{name}: inlet_temperature = {inlet_temperature} K; expected a positive temperature",
        name=name,
        inlet_temperature=inlet_temperature,
    )
    ops.check(
        ops.logical_and(ops.isfinite(pressure_ratio), pressure_ratio >= 1),
        PhysicsRangeError,
        "{name}: pressure_ratio = {pressure_ratio}; expected >= 1 (no expansion)",
        name=name,
        pressure_ratio=pressure_ratio,
    )
