"""Pump physics of this category: gas compression, the ESP efficiency and line-shaft curves.

The ESP and line-shaft curves are the TNO R11363 polynomials on the historical US basis
(``head``, with ``esp_efficiency`` the retained US-basis efficiency); the power polynomial lives
in ``gemini.physics.pumps`` because the doublet design reads it too. Compression is ideal-gas
adiabatic with an isentropic efficiency and intercooled stages.

The relations are the textbook ideal-gas forms used for compressor sizing, for example GPSA
Engineering Data Book, 14th ed. (2017), Section 13 "Compressors and Expanders", with the
compressibility factor Z = 1: the isentropic outlet temperature
``T_2s = T_1 * r**((k - 1) / k)`` and the actual adiabatic outlet temperature
``T_2 = T_1 + (T_2s - T_1) / eta_s``. They hold for gases near ideal behaviour (Z close to one,
low reduced pressure) with a constant heat capacity ratio ``k = cp / cv`` over the stage.
"""

from gemini import ops
from gemini.errors import PhysicsError
from gemini.ops import Constant
from gemini.physics import constants, units


@ops.physics
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
        PhysicsError,
        "isentropic_outlet_temperature: heat_capacity_ratio = {heat_capacity_ratio}; expected > 1",
        heat_capacity_ratio=heat_capacity_ratio,
    )
    return inlet_temperature * pressure_ratio ** ((heat_capacity_ratio - 1) / heat_capacity_ratio)


@ops.physics
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

    Validity: inlet_temperature positive, pressure_ratio at least one, heat_capacity_ratio greater
    than one, isentropic_efficiency in (0, 1]; other values raise PhysicsError. Ideal gas with
    Z = 1 and constant k.
    """
    ops.check(
        ops.logical_and(isentropic_efficiency > 0, isentropic_efficiency <= 1),
        PhysicsError,
        "stage_outlet_temperature: isentropic_efficiency = {isentropic_efficiency}; "
        "expected in (0, 1]",
        isentropic_efficiency=isentropic_efficiency,
    )
    ideal = isentropic_outlet_temperature(inlet_temperature, pressure_ratio, heat_capacity_ratio)
    return inlet_temperature + (ideal - inlet_temperature) / isentropic_efficiency


@ops.physics
def stage_pressure_ratio(pressure_ratio: float, stages: float) -> float:
    """Return the pressure ratio of each of several equal stages.

    Parameters
    ----------
    pressure_ratio : float
        Overall discharge over suction absolute pressure [-], positive.
    stages : float
        Number of equal stages [-], positive.

    Returns
    -------
    float
        ``r_stage = r ** (1 / N)`` [-].

    Notes
    -----
    Equal stage ratios minimise the work of an ideal intercooled compressor (GPSA Engineering
    Data Book, 14th ed. (2017), Section 13, multistage compression).
    """
    return pressure_ratio ** (1 / stages)


@ops.physics
def overall_pressure_ratio(discharge_pressure: float, suction_pressure: float) -> float:
    """Return the overall pressure ratio of a compressor.

    Parameters
    ----------
    discharge_pressure, suction_pressure : float
        Absolute discharge and suction pressure [Pa], suction positive.

    Returns
    -------
    float
        ``r = p_discharge / p_suction`` [-].

    Notes
    -----
    Reference: GPSA Engineering Data Book, 14th ed. (2017), Section 13, compression ratio.
    """
    return discharge_pressure / suction_pressure


@ops.physics
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
    inlet_temperature : float
        Suction temperature [K], positive.
    pressure_ratio : float
        Overall discharge over suction absolute pressure [-], at least one.
    heat_capacity_ratio : float
        Constant ``k = cp / cv`` [-], greater than one.
    isentropic_efficiency : float
        Isentropic efficiency of each stage [-], in (0, 1].
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
        ops.logical_and(specific_heat > 0, ops.logical_not(stages < 1)),
        PhysicsError,
        "specific_compression_work: specific_heat = {specific_heat} J/kg/K, stages = "
        "{stages}; expected a positive heat capacity and at least one stage",
        specific_heat=specific_heat,
        stages=stages,
    )
    _check_stage("specific_compression_work", inlet_temperature, pressure_ratio)
    outlet = stage_outlet_temperature(
        inlet_temperature,
        stage_pressure_ratio(pressure_ratio, stages),
        heat_capacity_ratio,
        isentropic_efficiency,
    )
    return stages * specific_heat * (outlet - inlet_temperature)


@ops.physics
def shaft_power(mass_flow: float, specific_work: float) -> float:
    """Return the shaft power of a compressor.

    Parameters
    ----------
    mass_flow : float
        Gas mass flow [kg/s].
    specific_work : float
        Shaft work per kg of gas [J/kg], from ``specific_compression_work``.

    Returns
    -------
    float
        ``P_shaft = m w`` [W].

    Notes
    -----
    Reference: GPSA Engineering Data Book, 14th ed. (2017), Section 13, gas horsepower.

    Validity: mass_flow nonnegative and specific_work real; no division occurs. Ideal gas, Z = 1, as
    for the work from ``specific_compression_work``.
    """
    return mass_flow * specific_work


@ops.physics
def heat_rejected(electricity: float, shaft_power: float, stages: float) -> float:
    """Return the heat an intercooled electric compressor rejects to its surroundings.

    Parameters
    ----------
    electricity : float
        Electricity drawn by the motor [W].
    shaft_power : float
        Shaft power of all stages [W].
    stages : float
        Number of equal stages [-], at least one.

    Returns
    -------
    float
        ``Q = P_el - P_shaft / N`` [W]: the intercooler duty ``(N - 1) P_shaft / N`` plus the
        motor loss ``P_el - P_shaft``.

    Notes
    -----
    Each of the N equal stages does ``P_shaft / N``; the intercoolers return the gas to the
    suction temperature, so only the last stage heat stays in the gas (GPSA Engineering Data
    Book, 14th ed. (2017), Section 13, intercooling).

    Validity: stages at least one (the code divides by it); electricity and shaft_power nonnegative
    with electricity at least shaft_power / stages.
    """
    return electricity - shaft_power / stages


def _check_stage(name, inlet_temperature, pressure_ratio):
    """Reject a nonpositive or non-finite temperature and a pressure ratio below one."""
    ops.check(
        ops.logical_and(ops.isfinite(inlet_temperature), inlet_temperature > 0),
        PhysicsError,
        "{name}: inlet_temperature = {inlet_temperature} K; expected a positive temperature",
        name=name,
        inlet_temperature=inlet_temperature,
    )
    ops.check(
        ops.logical_and(ops.isfinite(pressure_ratio), pressure_ratio >= 1),
        PhysicsError,
        "{name}: pressure_ratio = {pressure_ratio}; expected >= 1 (no expansion)",
        name=name,
        pressure_ratio=pressure_ratio,
    )


ESP_MIN_EFFICIENCY_POWER = Constant(
    "ESP_MIN_EFFICIENCY_POWER",
    0.1,
    "W",
    "shaft power below which the pump is treated as stopped and its efficiency as zero",
)


LINE_SHAFT_MIN_EFFICIENCY_POWER = Constant(
    "LINE_SHAFT_MIN_EFFICIENCY_POWER",
    0.1,
    "W",
    "pump power below which the pump is treated as stopped and its efficiency as zero",
)


HYDRAULIC_POWER_PER_HEAD = units.bhp_to_w(1) / units.ft_head_to_pa(1)
"""Unit factor of the ESP efficiency: [W per bhp] over [Pa per ft of head], computed once."""


@ops.physics
def head(volume_flow, frequency, stages, coefficients):
    """Return pressure rise [Pa] from flow [m3/s], frequency [Hz], stages and ft coefficients.

    The polynomial sum(c_i q^i) uses q in bbl/day and gives ft of head per stage at 60 Hz;
    head scales with the square of the frequency ratio.

    Valid for the fitted flow range of the coefficients and positive frequency and stages. The
    affinity law follows Takacs, Electrical Submersible Pumps Manual (2009); the polynomial
    form is the TNO R11363 pump correlation. The builtin ``sum`` over the coefficients is kept:
    it works on floats, arrays and traced values.
    """
    q = units.m3s_to_bbl_per_day(volume_flow)
    value = stages * (frequency / constants.ESP_REFERENCE_FREQUENCY) ** 2
    value *= sum(c * q**i for i, c in enumerate(coefficients))
    return units.ft_head_to_pa(value)


@ops.physics
def pump_efficiency(flow, head, power):
    """Return the SI efficiency of a pump from a measured or modelled power; zero when stopped.

    Parameters
    ----------
    flow : float
        Volume flow Q [m3/s].
    head : float
        Pressure rise H [Pa].
    power : float
        Pump power P [W]; below ``LINE_SHAFT_MIN_EFFICIENCY_POWER`` the efficiency is zero.

    Returns
    -------
    float
        ``eta = Q H / P`` [-].

    Notes
    -----
    Karassik et al., Pump Handbook, 4th ed., chapter 2. Not bitwise the same expression as
    ``esp_efficiency``, which keeps the US-basis factors of the retained ESP model.

    Validity: flow and head nonnegative; power at least LINE_SHAFT_MIN_EFFICIENCY_POWER (below it
    the result is zero), which keeps the divisor positive. The efficiency is in [0, 1] for a
    physical pump.
    """
    return ops.where(power >= LINE_SHAFT_MIN_EFFICIENCY_POWER, flow * head / power, 0.0)


@ops.physics
def esp_efficiency(flow, head, power):
    """Return the retained US-basis ESP efficiency; zero for a stopped pump.

    Parameters
    ----------
    flow : float
        Volume flow Q [m3/s].
    head : float
        Pressure rise H [Pa].
    power : float
        Shaft power P [W]; below ``ESP_MIN_EFFICIENCY_POWER`` the efficiency is zero.

    Returns
    -------
    float
        ``eta = Q[bbl/d] / 135773 * (H / P) * (W per bhp / Pa per ft)`` [-].

    Notes
    -----
    The factor 135773 is the historical ESP efficiency factor (``ESP_EFFICIENCY_FLOW_FACTOR``);
    the result is the SI ``Q H / P`` up to that factor. ``ops.truediv`` keeps the legacy float32
    arithmetic of the ESP: a plain ``/`` by a zero power raises in the plain scalar mode, where
    this function must return the discarded branch of ``ops.where`` instead.

    Validity: flow and head nonnegative; power at least ESP_MIN_EFFICIENCY_POWER (below it the
    result is zero), which keeps the divisor positive. The polynomial pump model can give a value
    above one.
    """
    return ops.where(
        power < ESP_MIN_EFFICIENCY_POWER,
        0.0,
        units.m3s_to_bbl_per_day(flow)
        / constants.ESP_EFFICIENCY_FLOW_FACTOR
        * ops.truediv(head, power)
        * HYDRAULIC_POWER_PER_HEAD,
    )


@ops.physics
def line_shaft_friction_power(friction_loss, depth, speed):
    """Return the mechanical friction power of a line shaft.

    Parameters
    ----------
    friction_loss : float
        Friction power per shaft length at the catalogue speed [W/m].
    depth : float
        Shaft length [m].
    speed : float
        Speed ratio [-].

    Returns
    -------
    float
        ``P_f = k L s`` [W].

    Notes
    -----
    Friction grows in proportion to speed (constant bearing friction torque), the form of the
    manufacturer tables of line-shaft friction in ANSI/HI 2.3, Rotodynamic Vertical Pumps for
    Design and Application.

    Validity: friction_loss, depth and speed nonnegative; no division occurs. Friction in proportion
    to speed holds for constant bearing friction torque.
    Source: The form of the manufacturer line-shaft friction tables cited in ANSI/HI 2.3,
    Rotodynamic Vertical Pumps for Design and Application, as cited for the line-shaft pump model.
    """
    return friction_loss * depth * speed
