"""Moist-air psychrometrics: saturation pressure, dew point, humidity ratio and wet bulb.

All functions take SI inputs: absolute temperature [K], relative humidity as a fraction [-] and
absolute pressure [Pa]. Moist air is treated as an ideal mixture of dry air and water vapour
without the enhancement factor, which ASHRAE Fundamentals includes in its tabulated saturation
humidity ratios (about 0.4 % at sea level); see ``humidity_ratio``.
"""

from gemini import ops
from gemini.errors import PhysicsRangeError

MINIMUM_TEMPERATURE = 173.15
"""Lower validity limit [K] of the Hyland-Wexler equation over ice (-100 degC)."""

MAXIMUM_TEMPERATURE = 473.15
"""Upper validity limit [K] of the Hyland-Wexler equation over liquid water (200 degC)."""

MOLAR_MASS_RATIO = 0.621945
"""Ratio of the molar masses of water vapour and dry air [-] (ASHRAE Fundamentals, eq. 20)."""

_ICE = (-5.6745359e3, 6.3925247, -9.6778430e-3, 6.2215701e-7, 2.0747825e-9, -9.4840240e-13)
_ICE_LOG = 4.1635019
_WATER = (-5.8002206e3, 1.3914993, -4.8640239e-2, 4.1764768e-5, -1.4452093e-8)
_WATER_LOG = 6.5459673


def saturation_pressure(temperature: float) -> float:
    """Return the saturation pressure of water vapour [Pa] over ice or liquid water.

    Parameters
    ----------
    temperature : float
        Absolute temperature [K], from 173.15 K (-100 degC) to 473.15 K (200 degC).

    Returns
    -------
    float
        Saturation vapour pressure [Pa]: over ice below 0 degC, over liquid water from 0 degC.

    Notes
    -----
    Hyland, R.W. and Wexler, A. (1983), "Formulations for the thermodynamic properties of the
    saturated phases of H2O from 173.15 K to 473.15 K", ASHRAE Transactions 89(2A), as given in
    ASHRAE Handbook - Fundamentals (2017), chapter 1, equations 5 (ice, -100 to 0 degC) and 6
    (liquid water, 0 to 200 degC):

    ln p_ws = C1/T + C2 + C3 T + C4 T^2 + C5 T^3 + C6 T^4 + C7 ln T  (ice)
    ln p_ws = C8/T + C9 + C10 T + C11 T^2 + C12 T^3 + C13 ln T       (liquid water)

    They agree with the IAPWS-95 based ASHRAE table values within 3e-4 relative.
    """
    _check_temperature("saturation_pressure", temperature)
    return _saturation_pressure(temperature)


def dew_point(temperature: float, relative_humidity: float) -> float:
    """Return the dew-point temperature [K] of moist air.

    Parameters
    ----------
    temperature : float
        Dry-bulb temperature [K], from 173.15 K to 473.15 K.
    relative_humidity : float
        Relative humidity [-] in (0, 1], the vapour pressure over ``saturation_pressure``.

    Returns
    -------
    float
        Temperature [K] at which ``saturation_pressure`` equals the vapour pressure
        ``relative_humidity * saturation_pressure(temperature)``; below 0 degC this is the frost
        point over ice, as in ASHRAE Fundamentals (2017), chapter 1, equations 39 and 40.

    Notes
    -----
    The Hyland-Wexler saturation pressure is inverted with Brent's method to 1e-9 K instead of
    the ASHRAE fitted dew-point polynomial, so the result is consistent with
    ``saturation_pressure`` by construction. A vapour pressure below the saturation pressure at
    -100 degC raises ``PhysicsRangeError``.
    """
    _check_temperature("dew_point", temperature)
    _check_relative_humidity("dew_point", relative_humidity)
    vapour_pressure = relative_humidity * saturation_pressure(temperature)
    ops.check(
        ops.logical_or(
            relative_humidity == 1, vapour_pressure >= saturation_pressure(MINIMUM_TEMPERATURE)
        ),
        PhysicsRangeError,
        "dew_point: vapour pressure = {vapour_pressure} Pa at temperature = {temperature} K "
        "and relative_humidity = {relative_humidity}; expected a dew point above "
        "{minimum} K",
        vapour_pressure=vapour_pressure,
        temperature=temperature,
        relative_humidity=relative_humidity,
        minimum=MINIMUM_TEMPERATURE,
    )
    point = ops.brentq(
        _saturation_residual,
        MINIMUM_TEMPERATURE,
        temperature,
        args=(vapour_pressure,),
        xtol=1e-9,
    )
    return ops.where(relative_humidity == 1, temperature, point)


def _saturation_pressure(temperature):
    """Return the Hyland-Wexler saturation pressure [Pa] without checking the temperature.

    Both the ice and the liquid-water branch are evaluated and ``where`` selects one.
    """
    ice = ops.exp(_polynomial(_ICE, temperature) + _ICE_LOG * ops.log(temperature))
    water = ops.exp(_polynomial(_WATER, temperature) + _WATER_LOG * ops.log(temperature))
    return ops.where(temperature < 273.15, ice, water)


def _saturation_residual(point, vapour_pressure):
    """Return the saturation pressure at ``point`` minus ``vapour_pressure`` [Pa].

    The temperature is not checked: a solver evaluates every row, also one whose own check
    reports the error.
    """
    return _saturation_pressure(point) - vapour_pressure


def humidity_ratio(temperature: float, relative_humidity: float, pressure: float) -> float:
    """Return the humidity ratio [kg water vapour per kg dry air] of moist air.

    Parameters
    ----------
    temperature : float
        Dry-bulb temperature [K], from 173.15 K to 473.15 K.
    relative_humidity : float
        Relative humidity [-] in [0, 1].
    pressure : float
        Total absolute pressure [Pa], above the vapour pressure.

    Returns
    -------
    float
        W = 0.621945 p_w / (p - p_w) with p_w = relative_humidity * saturation_pressure(T).

    Notes
    -----
    ASHRAE Handbook - Fundamentals (2017), chapter 1, equations 20 and 22, for an ideal mixture.
    The enhancement factor (about 1.004 at sea level) is neglected, so the saturated values are
    about 0.4 % below the ASHRAE table column W_s.
    """
    _check_temperature("humidity_ratio", temperature)
    _check_relative_humidity("humidity_ratio", relative_humidity, minimum_included=True)
    vapour_pressure = relative_humidity * saturation_pressure(temperature)
    ops.check(
        pressure > vapour_pressure,
        PhysicsRangeError,
        "humidity_ratio: pressure = {pressure} Pa; expected more than the vapour pressure "
        "{vapour_pressure} Pa",
        pressure=pressure,
        vapour_pressure=vapour_pressure,
    )
    return MOLAR_MASS_RATIO * vapour_pressure / (pressure - vapour_pressure)


def wet_bulb_temperature(temperature: float, relative_humidity: float) -> float:
    """Return the psychrometric wet-bulb temperature [K] at standard sea-level pressure.

    Parameters
    ----------
    temperature : float
        Dry-bulb temperature [K], from 253.15 K (-20 degC) to 323.15 K (50 degC).
    relative_humidity : float
        Relative humidity [-], from 0.05 to 0.99.

    Returns
    -------
    float
        Wet-bulb temperature [K].

    Notes
    -----
    Stull, R. (2011), "Wet-bulb temperature from relative humidity and air temperature",
    Journal of Applied Meteorology and Climatology 50, 2267-2269, with T in degC and RH in %:

    Tw = T atan(0.151977 (RH + 8.313659)^0.5) + atan(T + RH) - atan(RH - 1.676331)
         + 0.00391838 RH^1.5 atan(0.023101 RH) - 4.686035

    Fitted at 101.325 kPa; the error is between -1 and +0.65 K over the validity range, mostly
    within 0.3 K. Stull notes that cold and very dry combinations (low wet-bulb, below his
    figure's curve) are less accurate; inputs outside the stated ranges raise
    ``PhysicsRangeError``.
    """
    _check_number("wet_bulb_temperature", temperature=temperature)
    _check_number("wet_bulb_temperature", relative_humidity=relative_humidity)
    ops.check(
        ops.logical_and(
            ops.logical_and(temperature >= 253.15, temperature <= 323.15),
            ops.logical_and(relative_humidity >= 0.05, relative_humidity <= 0.99),
        ),
        PhysicsRangeError,
        "wet_bulb_temperature: temperature = {temperature} K, relative_humidity = "
        "{relative_humidity}; expected 253.15 K to 323.15 K and 0.05 to 0.99",
        temperature=temperature,
        relative_humidity=relative_humidity,
    )
    celsius = temperature - 273.15
    percent = 100 * relative_humidity
    wet_bulb = (
        celsius * ops.atan(0.151977 * ops.sqrt(percent + 8.313659))
        + ops.atan(celsius + percent)
        - ops.atan(percent - 1.676331)
        + 0.00391838 * percent**1.5 * ops.atan(0.023101 * percent)
        - 4.686035
    )
    return wet_bulb + 273.15


def _polynomial(coefficients, temperature):
    """Return C1/T + C2 + C3 T + C4 T^2 + ... for the Hyland-Wexler coefficients."""
    inverse, *powers = coefficients
    return inverse / temperature + sum(c * temperature**n for n, c in enumerate(powers))


def _check_number(function, **values):
    """Reject NaN inputs, which would otherwise return NaN as if it were a valid result."""
    for name, value in values.items():
        ops.check(
            ops.logical_not(ops.isnan(value)),
            PhysicsRangeError,
            "{function}: {name} = nan; expected a number",
            function=function,
            name=name,
            value=value,
        )


def _check_temperature(function, temperature):
    """Require a temperature inside the Hyland-Wexler range."""
    _check_number(function, temperature=temperature)
    ops.check(
        ops.logical_and(temperature >= MINIMUM_TEMPERATURE, temperature <= MAXIMUM_TEMPERATURE),
        PhysicsRangeError,
        "{function}: temperature = {temperature} K; expected {minimum} K to {maximum} K",
        function=function,
        temperature=temperature,
        minimum=MINIMUM_TEMPERATURE,
        maximum=MAXIMUM_TEMPERATURE,
    )


def _check_relative_humidity(function, relative_humidity, minimum_included=False):
    """Require a relative humidity in (0, 1], or in [0, 1] when zero is meaningful."""
    _check_number(function, relative_humidity=relative_humidity)
    valid = ops.logical_and(relative_humidity <= 1, relative_humidity >= 0)
    if not minimum_included:
        valid = ops.logical_and(valid, relative_humidity > 0)
    ops.check(
        valid,
        PhysicsRangeError,
        "{function}: relative_humidity = {relative_humidity}; expected a fraction in {expected}",
        function=function,
        relative_humidity=relative_humidity,
        expected="[0, 1]" if minimum_included else "(0, 1]",
    )
