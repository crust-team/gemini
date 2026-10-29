"""Heat pump and chiller relations: Carnot COPs, sorption characteristic equations, part load.

All functions take and return SI values (K, W, W/K). The characteristic equation of sorption
machines is defined on Celsius temperatures; ``characteristic_temperature_difference`` converts
its kelvin inputs internally.
"""

import math

from gemini.core.physics.units import k_to_c
from gemini.errors import PhysicsRangeError


def carnot_cop_heating(
    sink_temperature: float, source_temperature: float, minimum_lift: float = 0.0
) -> float:
    """Return the Carnot heating COP of a heat pump.

    Parameters
    ----------
    sink_temperature, source_temperature : float
        Absolute temperatures [K] at which heat is delivered and taken up.
    minimum_lift : float
        Lift floor [K]: the lift used is ``max(sink - source, minimum_lift)``.

    Returns
    -------
    float
        COP_h = T_sink / (T_sink - T_source) [-], with the floored lift.

    Notes
    -----
    Reference: Carnot efficiency of a reversible heat pump, for example Moran and Shapiro,
    Fundamentals of Engineering Thermodynamics, chapter 5. Valid for any positive temperatures
    whose (floored) lift is positive; the floor bounds the COP of nearly equal temperatures.
    """
    lift = _lift("carnot_cop_heating", sink_temperature, source_temperature, minimum_lift)
    return sink_temperature / lift


def carnot_cop_cooling(
    sink_temperature: float, source_temperature: float, minimum_lift: float = 0.0
) -> float:
    """Return the Carnot cooling COP (energy efficiency ratio) of a chiller.

    Parameters
    ----------
    sink_temperature, source_temperature : float
        Absolute temperatures [K] at which heat is rejected and taken up (the cold side).
    minimum_lift : float
        Lift floor [K]: the lift used is ``max(sink - source, minimum_lift)``.

    Returns
    -------
    float
        COP_c = T_source / (T_sink - T_source) [-], with the floored lift.

    Notes
    -----
    Reference: Carnot efficiency of a reversible refrigerator, for example Moran and Shapiro,
    Fundamentals of Engineering Thermodynamics, chapter 5. COP_c = COP_h - 1 for the same lift.
    """
    lift = _lift("carnot_cop_cooling", sink_temperature, source_temperature, minimum_lift)
    return source_temperature / lift


def characteristic_temperature_difference(
    generator_temperature: float,
    rejection_temperature: float,
    evaporator_temperature: float,
    rejection_coefficient: float,
    evaporator_coefficient: float,
) -> float:
    """Return the characteristic temperature difference of a sorption machine.

    Parameters
    ----------
    generator_temperature, rejection_temperature, evaporator_temperature : float
        External temperatures [K] of the driving (generator or desorber), the heat-rejection
        (absorber or adsorber plus condenser) and the chilled (evaporator) circuits.
    rejection_coefficient, evaporator_coefficient : float
        Fitted coefficients ``a`` and ``r`` [-] of the characteristic equation.

    Returns
    -------
    float
        ddt = t_G - a * t_AC + r * t_E [K], evaluated with Celsius temperatures.

    Notes
    -----
    Reference: Hellmann, Schweigler and Ziegler (1999), "The characteristic equations of
    absorption chillers", Proc. Int. Sorption Heat Pump Conference, Munich; Kuehn and Ziegler
    (2005), "Operational results of a 10 kW absorption chiller and adaptation of the
    characteristic equation", Proc. 1st Int. Conf. Solar Air Conditioning. For the ideal Duehring
    form a = 1 + B and r = B (B about 1.1 to 1.2 for water/LiBr); fitted values differ, so the
    equation is evaluated on the Celsius basis of the published fits.
    """
    _check_numbers(
        "characteristic_temperature_difference",
        generator_temperature=generator_temperature,
        rejection_temperature=rejection_temperature,
        evaporator_temperature=evaporator_temperature,
        rejection_coefficient=rejection_coefficient,
        evaporator_coefficient=evaporator_coefficient,
    )
    return (
        k_to_c(generator_temperature)
        - rejection_coefficient * k_to_c(rejection_temperature)
        + evaporator_coefficient * k_to_c(evaporator_temperature)
    )


def characteristic_evaporator_duty(
    driving_difference: float,
    minimum_driving_difference: float,
    slope: float,
    sensitivity: float,
) -> float:
    """Return the evaporator duty [W] of a sorption machine from its characteristic equation.

    Parameters
    ----------
    driving_difference : float
        Characteristic temperature difference [K] at the circuit inlet temperatures.
    minimum_driving_difference : float
        Threshold ddt_min [K] at which the machine stops producing cold.
    slope : float
        Nonnegative slope s [W/K] of the evaporator duty over ddt.
    sensitivity : float
        Nonnegative k [K/W]: how much ddt at the circuit mean temperatures falls per watt of
        evaporator duty (see ``characteristic_sensitivity``); ``inf`` for a stopped circuit.

    Returns
    -------
    float
        Q_E = max(0, s * (ddt_in - ddt_min) / (1 + s * k)) [W].

    Notes
    -----
    The characteristic equation Q_E = s * (ddt_mean - ddt_min) uses the arithmetic mean
    temperatures of the external circuits (Hellmann, Schweigler and Ziegler 1999). Because the
    mean temperatures move linearly with the duties, ddt_mean = ddt_in - k * Q_E, and the
    equation is solved here in closed form from the inlet temperatures.
    """
    _check_numbers(
        "characteristic_evaporator_duty",
        driving_difference=driving_difference,
        minimum_driving_difference=minimum_driving_difference,
        slope=slope,
        sensitivity=sensitivity,
    )
    if slope < 0 or sensitivity < 0:
        raise PhysicsRangeError(
            f"characteristic_evaporator_duty: slope = {slope} W/K, sensitivity = "
            f"{sensitivity} K/W; expected both >= 0"
        )
    if math.isinf(sensitivity) or driving_difference <= minimum_driving_difference:
        return 0.0
    return slope * (driving_difference - minimum_driving_difference) / (1 + slope * sensitivity)


def characteristic_sensitivity(
    generator_rate: float,
    rejection_rate: float,
    evaporator_rate: float,
    generator_ratio: float,
    rejection_ratio: float,
    rejection_coefficient: float,
    evaporator_coefficient: float,
) -> float:
    """Return how much the mean-temperature ddt falls per watt of evaporator duty [K/W].

    Parameters
    ----------
    generator_rate, rejection_rate, evaporator_rate : float
        Nonnegative heat capacity rates m_dot * cp [W/K] of the three external circuits.
    generator_ratio, rejection_ratio : float
        Generator and heat-rejection duty per unit evaporator duty [-], Q_G / Q_E and
        Q_AC / Q_E.
    rejection_coefficient, evaporator_coefficient : float
        Coefficients ``a`` and ``r`` [-] of the characteristic equation.

    Returns
    -------
    float
        k = Q_G/Q_E / (2 C_G) + a * Q_AC/Q_E / (2 C_AC) + r / (2 C_E) [K/W]; ``inf`` when a
        circuit is stopped, since it then cannot carry any duty.

    Notes
    -----
    Each circuit's mean temperature moves by half its temperature change Q / C. The driving
    circuit cools, the heat-rejection circuit warms and the chilled circuit cools as the
    evaporator duty rises; all three lower ddt for positive coefficients.
    """
    rates = dict(
        generator_rate=generator_rate,
        rejection_rate=rejection_rate,
        evaporator_rate=evaporator_rate,
    )
    _check_numbers("characteristic_sensitivity", **rates)
    if min(rates.values()) < 0:
        raise PhysicsRangeError(
            f"characteristic_sensitivity: capacity rates {rates} W/K; expected all >= 0"
        )
    if min(rates.values()) == 0:
        return math.inf
    return (
        generator_ratio / (2 * generator_rate)
        + rejection_coefficient * rejection_ratio / (2 * rejection_rate)
        + evaporator_coefficient / (2 * evaporator_rate)
    )


def sorption_evaporator_capacity(
    generator_temperature: float,
    rejection_temperature: float,
    evaporator_temperature: float,
    generator_rate: float,
    rejection_rate: float,
    evaporator_rate: float,
    *,
    slope: float,
    minimum_driving_difference: float,
    rejection_coefficient: float,
    evaporator_coefficient: float,
    thermal_cop: float,
    auxiliary_power_ratio: float,
) -> float:
    """Return the largest evaporator duty [W] a sorption chiller delivers at these inlets.

    Parameters
    ----------
    generator_temperature, rejection_temperature, evaporator_temperature : float
        Inlet temperatures [K] of the driving, heat-rejection and chilled circuits.
    generator_rate, rejection_rate, evaporator_rate : float
        Nonnegative heat capacity rates m_dot * cp [W/K] of the same circuits.
    slope, minimum_driving_difference : float
        Characteristic slope s [W/K] and threshold ddt_min [K].
    rejection_coefficient, evaporator_coefficient : float
        Characteristic coefficients ``a`` and ``r`` [-].
    thermal_cop : float
        Positive thermal COP Q_E / Q_G [-].
    auxiliary_power_ratio : float
        Nonnegative pump and auxiliary electricity per unit evaporator duty [-]; it ends up in
        the heat-rejection circuit.

    Returns
    -------
    float
        Q_E from ``characteristic_evaporator_duty`` with the inlet ddt and the mean-temperature
        sensitivity of the duty ratios Q_G / Q_E = 1 / COP and
        Q_AC / Q_E = 1 + 1 / COP + auxiliary_power_ratio.

    Notes
    -----
    Reference: Hellmann, Schweigler and Ziegler (1999) for the characteristic equation; the
    constant thermal COP is a simplification of its separate generator equation, reasonable
    away from the threshold where the measured COP of single-effect machines is nearly flat.
    """
    if thermal_cop <= 0 or auxiliary_power_ratio < 0:
        raise PhysicsRangeError(
            f"sorption_evaporator_capacity: thermal_cop = {thermal_cop}, auxiliary_power_ratio "
            f"= {auxiliary_power_ratio}; expected thermal_cop > 0 and auxiliary_power_ratio >= 0"
        )
    generator_ratio = 1 / thermal_cop
    driving = characteristic_temperature_difference(
        generator_temperature,
        rejection_temperature,
        evaporator_temperature,
        rejection_coefficient,
        evaporator_coefficient,
    )
    sensitivity = characteristic_sensitivity(
        generator_rate,
        rejection_rate,
        evaporator_rate,
        generator_ratio,
        1 + generator_ratio + auxiliary_power_ratio,
        rejection_coefficient,
        evaporator_coefficient,
    )
    return characteristic_evaporator_duty(driving, minimum_driving_difference, slope, sensitivity)


def part_load_duty(requested: float, capacity: float, minimum_part_load: float) -> float:
    """Return the duty [W] a capacity-limited machine with a minimum part load delivers.

    Parameters
    ----------
    requested : float
        Nonnegative duty [W] asked for by the setpoint.
    capacity : float
        Positive rated duty [W].
    minimum_part_load : float
        Smallest steady load as a fraction of capacity [-], in [0, 1].

    Returns
    -------
    float
        min(requested, capacity), or 0 when that is below minimum_part_load * capacity.

    Notes
    -----
    Below the minimum part load the machine is taken as switched off for the step rather than
    cycling on and off; at hourly steps this underestimates the delivered heat of a cycling
    machine. EN 14825 (seasonal performance of heat pumps and chillers) describes the cycling
    alternative with a degradation coefficient.
    """
    _check_numbers(
        "part_load_duty",
        requested=requested,
        capacity=capacity,
        minimum_part_load=minimum_part_load,
    )
    if requested < 0 or capacity <= 0 or not 0 <= minimum_part_load <= 1:
        raise PhysicsRangeError(
            f"part_load_duty: requested = {requested} W, capacity = {capacity} W, "
            f"minimum_part_load = {minimum_part_load}; expected requested >= 0, capacity > 0 "
            "and minimum_part_load in [0, 1]"
        )
    duty = min(requested, capacity)
    if duty < minimum_part_load * capacity:
        return 0.0
    return duty


def _lift(function, sink_temperature, source_temperature, minimum_lift):
    """Return the floored temperature lift [K]; reject nonpositive temperatures and lifts."""
    _check_numbers(
        function,
        sink_temperature=sink_temperature,
        source_temperature=source_temperature,
        minimum_lift=minimum_lift,
    )
    if sink_temperature <= 0 or source_temperature <= 0 or minimum_lift < 0:
        raise PhysicsRangeError(
            f"{function}: sink_temperature = {sink_temperature} K, source_temperature = "
            f"{source_temperature} K, minimum_lift = {minimum_lift} K; expected positive "
            "temperatures and minimum_lift >= 0"
        )
    lift = sink_temperature - source_temperature
    if max(lift, minimum_lift) <= 0:
        raise PhysicsRangeError(
            f"{function}: lift = {lift} K, minimum_lift = {minimum_lift} K; expected "
            "sink_temperature above source_temperature or a positive minimum_lift"
        )
    return max(lift, minimum_lift)


def _check_numbers(function, **values):
    """Reject NaN inputs, which would otherwise return NaN as if it were a valid result."""
    for name, value in values.items():
        if math.isnan(value):
            raise PhysicsRangeError(f"{function}: {name} = nan; expected a number")
