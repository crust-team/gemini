"""CO2 corrosion correlations (NORSOK M-506, de Waard–Lotz 1991/1995) and wall-loss helpers.

``co2_corrosion_rate`` is the SI boundary. The correlations work in their published basis:
temperature in degC, pressures in bar, NORSOK water flow in m3/day, viscosity in cP,
bicarbonate in mg/l and ionic strength in g/l. Rates are in mm/year, the explicit
literature-unit exception of the package.
"""

import bisect
import itertools
import math
from dataclasses import dataclass
from typing import Literal

import numpy as np

from gemini.errors import MissingChemistryError, PhysicsRangeError, UnknownCorrelationError
from gemini.utils.strings import did_you_mean, join_names

from . import geometry, units

_DEFAULT_COEFFICIENTS = {
    "NORSOK": {"A": 1},
    "DLM": {"A": 5.8, "B": 1710, "C": 0.67},
    "DLD": {"A": 4.93, "B": 1119, "C": 0.58, "D": 2.45},
}
"""Published correlation constants; fitted variants may replace them."""

_FUGACITY_PRESSURE_CAP = 250
"""Pressure [bar] above which the fugacity coefficient stays at its 250 bar value."""

_KT_TEMPERATURES = (5, 15, 20, 40, 60, 80, 90, 120, 150)
_KT_VALUES = (0.42, 1.59, 4.762, 8.927, 10.695, 9.949, 6.250, 7.770, 5.203)

_BICARBONATE_MOLAR_MASS = 61.2
"""Bicarbonate molar mass [g/mol] of the original NORSOK implementation.

HCO3- is 61.02 g/mol; the retained 61.2 keeps the captured goldens.
"""

_SALT_MOLAR_MASS = 58.44
"""NaCl molar mass [g/mol] converting ionic strength from g/l to mol/l."""

_NEWTON_TOLERANCE = 10**-6
_NEWTON_MAX_ITERATIONS = 100
_NO_ROOT_PH = 99.99

_PH_FACTOR = {
    5.0: (
        (4.6, lambda ph: 2.0676 + 0.2309 * ph),
        (6.5, lambda ph: 4.342 - 1.061 * ph + 0.0708 * ph**2),
    ),
    15.0: (
        (4.6, lambda ph: 2.0676 - 0.2309 * ph),
        (6.5, lambda ph: 4.986 - 1.191 * ph + 0.0708 * ph**2),
    ),
    20.0: (
        (4.6, lambda ph: 2.0676 - 0.2309 * ph),
        (6.5, lambda ph: 5.1885 - 1.2353 * ph + 0.0708 * ph**2),
    ),
    40.0: (
        (4.6, lambda ph: 2.0676 - 0.2309 * ph),
        (6.5, lambda ph: 5.1885 - 1.2353 * ph + 0.0708 * ph**2),
    ),
    60.0: (
        (4.6, lambda ph: 1.836 - 0.1818 * ph),
        (6.5, lambda ph: 15.444 - 6.1291 * ph + 0.8204 * ph**2 - 0.0371 * ph**3),
    ),
    80.0: (
        (4.6, lambda ph: 2.6727 - 0.3636 * ph),
        (6.5, lambda ph: 331.68 * math.exp(-1.2618 * ph)),
    ),
    90.0: (
        (4.57, lambda ph: 3.1355 - 0.4673 * ph),
        (5.62, lambda ph: 21254 * math.exp(-2.1811 * ph)),
        (6.5, lambda ph: 0.4014 - 0.0538 * ph),
    ),
    120.0: (
        (4.3, lambda ph: 1.5375 - 0.125 * ph),
        (5.0, lambda ph: 5.9757 - 1.157 * ph),
        (6.5, lambda ph: 0.546125 - 0.071225 * ph),
    ),
    150.0: (
        (3.8, lambda ph: 1),
        (5.0, lambda ph: 17.634 - 7.0945 * ph + 0.715 * ph**2),
        (6.5, lambda ph: 0.037),
    ),
}
"""NORSOK M-506 pH factor per tabulated temperature [degC]: ``(upper pH, formula)`` segments.

Each segment applies from the previous upper bound (exclusive), or pH 3.5 (inclusive), up to
its own upper bound (inclusive).
"""


@dataclass(frozen=True)
class _Conditions:
    """CO2-corrosion inputs in the correlations' basis.

    Temperature [degC], pressure, CO2 partial pressure and fugacity [bar], flow rate [m3/s],
    NORSOK water flow rate [m3/day], water density [kg/m3], water viscosity [cP], diameter
    and roughness [m], bicarbonate concentration [mg/l] and ionic strength [g/l].
    """

    temperature: float
    pressure: float
    co2_pressure: float
    fugacity: float
    flow_rate: float
    water_flow_rate: float
    water_density: float
    water_viscosity: float
    diameter: float
    roughness: float
    bicarb_concentration: float
    ionic_strength: float


def co2_corrosion_rate(
    model: Literal["NORSOK", "DLM", "DLD"],
    *,
    fitted: bool = False,
    temperature: float,
    pressure: float,
    water_flow_rate: float,
    water_density: float = 1000,
    water_viscosity: float = 0.001,
    diameter: float = 0.1,
    roughness: float = 0.00005,
    co2_fraction: float | None = None,
    co2_partial_pressure: float | None = None,
    bicarb_concentration: float = 0.268,
    ionic_strength: float = 71,
    coefficients: dict[str, float] | None = None,
) -> float:
    """Evaluate the original CO2 correlation through an SI boundary.

    Parameters
    ----------
    model : str
        NORSOK M-506, DLM (1991), or DLD (1995).
    fitted : bool
        Select the original fitted variant; coefficients default to published values.
        Without ``fitted`` the published values apply and ``coefficients`` is ignored.
    temperature, pressure : float
        Temperature [K] and absolute pressure [Pa].
    water_flow_rate, water_density, water_viscosity : float
        Liquid flow [m3/s], density [kg/m3], viscosity [Pa s]. NORSOK and DLD need a
        nonzero flow; DLM does not use it.
    diameter, roughness : float
        Pipe inner diameter and roughness [m].
    co2_fraction, co2_partial_pressure : float, optional
        Gas mole fraction [-] or CO2 partial pressure [Pa]; pressure takes precedence. The
        resulting CO2 partial pressure must be positive.
    bicarb_concentration, ionic_strength : float
        Bicarbonate and salt concentrations [kg/m3].
    coefficients : dict, optional
        Fitted correlation constants in their original empirical basis.

    Returns
    -------
    float
        Wall penetration rate [mm/year].

    Notes
    -----
    NOTE(refactor): NORSOK retains exact-temperature pH branches and fallback 7 (see
    ``_ph_factor``). A NORSOK pH solve that does not converge also keeps its last iterate
    without a warning (see ``_hydrogen_ion``).
    """
    if model not in _RATES:
        raise UnknownCorrelationError(
            f"co2_corrosion_rate: model = {model!r}; expected one of "
            f"{join_names(_RATES)}{did_you_mean(model, _RATES)}"
        )
    if fitted:
        coefficients = _DEFAULT_COEFFICIENTS[model] | (coefficients or {})
    else:
        coefficients = _DEFAULT_COEFFICIENTS[model]
    conditions = _conditions(
        model,
        temperature=units.k_to_c(temperature),
        pressure=units.pa_to_bar(pressure),
        co2_fraction=co2_fraction,
        co2_partial_pressure=co2_partial_pressure,
        flow_rate=water_flow_rate,
        water_density=water_density,
        water_viscosity=units.pas_to_cp(water_viscosity),
        diameter=diameter,
        roughness=roughness,
        bicarb_concentration=units.kgm3_to_mgl(bicarb_concentration),
        ionic_strength=ionic_strength,
    )
    rate = _RATES[model](conditions, coefficients)
    if isinstance(rate, complex):
        raise PhysicsRangeError(
            f"co2_corrosion_rate {model}: water_flow_rate = {water_flow_rate} m3/s gives a "
            "complex rate; expected a nonnegative flow"
        )
    return float(rate)


def _conditions(model, *, co2_fraction, co2_partial_pressure, **values):
    """Resolve the CO2 partial pressure and fugacity [bar] and check the correlation domain.

    ``co2_partial_pressure`` [Pa] takes precedence over ``co2_fraction`` times pressure.
    """
    if co2_partial_pressure is not None:
        co2_pressure = units.pa_to_bar(co2_partial_pressure)
    elif co2_fraction is not None:
        co2_pressure = co2_fraction * values["pressure"]
    else:
        raise MissingChemistryError(
            f"co2_corrosion_rate {model}: co2_fraction and co2_partial_pressure are None; "
            "expected one of them"
        )
    if co2_pressure <= 0:
        raise PhysicsRangeError(
            f"co2_corrosion_rate {model}: CO2 partial pressure = {co2_pressure} bar; expected "
            "a positive value (the correlations take its logarithm)"
        )
    if values["flow_rate"] == 0 and model != "DLM":
        raise PhysicsRangeError(
            f"co2_corrosion_rate {model}: water_flow_rate = 0 m3/s; expected a nonzero flow "
            "(the flow-dependent correlations divide by the flow velocity)"
        )
    return _Conditions(
        co2_pressure=co2_pressure,
        fugacity=_co2_fugacity(values["temperature"], values["pressure"], co2_pressure),
        water_flow_rate=units.m3s_to_m3day(values["flow_rate"]),
        **values,
    )


def _co2_fugacity(temperature, pressure, co2_pressure):
    """Return the CO2 fugacity [bar] from temperature [degC] and pressures [bar].

    The fugacity coefficient 10^(p (0.0031 - 1.4/T)) is evaluated at no more than 250 bar,
    the validity limit of the de Waard–Lotz fit.
    """
    temperature_kelvin = units.c_to_k(temperature)
    capped = pressure if pressure <= _FUGACITY_PRESSURE_CAP else _FUGACITY_PRESSURE_CAP
    fugacity_coefficient = 10 ** (capped * (0.0031 - 1.4 / temperature_kelvin))
    return fugacity_coefficient * co2_pressure


def _scaling_factor(temperature, fugacity, exponent):
    """Return the de Waard–Lotz protective-scale factor at temperature [degC].

    The factor 10^(2400/T - exponent log f - 6.7), at most one, applies above the scaling
    temperature 2400 / (6.7 + 0.6 log f); DLM uses exponent 0.6 and DLD 0.44.
    """
    temperature_kelvin = units.c_to_k(temperature)
    threshold = 2400 / (6.7 + 0.6 * math.log10(fugacity))
    factor = 10 ** (2400 / temperature_kelvin - exponent * math.log10(fugacity) - 6.7)
    return min(factor, 1) if temperature_kelvin >= threshold else 1


def _dlm_rate(conditions, coefficients):
    """Return the de Waard–Lotz–Milliams (1991) rate [mm/year].

    Reference: "Predictive Model for CO2 Corrosion Engineering in Wet Natural Gas
    Pipelines", https://doi.org/10.5006/1.3585212.
    """
    temperature_kelvin = units.c_to_k(conditions.temperature)
    a, b, c = coefficients["A"], coefficients["B"], coefficients["C"]
    return 10 ** (
        a - b / temperature_kelvin + c * math.log10(conditions.fugacity)
    ) * _scaling_factor(conditions.temperature, conditions.fugacity, 0.6)


def _dld_rate(conditions, coefficients):
    """Return the de Waard–Lotz–Dugstad (1995) rate [mm/year].

    Reaction and mass-transfer limited rates combine in series. Reference: "Influence of
    liquid flow velocity on CO2 corrosion: A semi-empirical model",
    https://www.osti.gov/biblio/106125.
    """
    temperature_kelvin = units.c_to_k(conditions.temperature)
    fugacity = conditions.fugacity
    reaction = 10 ** (
        coefficients["A"]
        - coefficients["B"] / temperature_kelvin
        + coefficients["C"] * math.log10(fugacity)
    )
    velocity = conditions.flow_rate / geometry.circle_area(conditions.diameter)
    mass_transfer = coefficients["D"] * (velocity**0.8 / conditions.diameter**0.2) * fugacity
    rate = 1 / (1 / reaction + 1 / mass_transfer)
    return rate * _scaling_factor(conditions.temperature, fugacity, 0.44)


def _norsok_rate(conditions, coefficients):
    """Return the NORSOK M-506 rate [mm/year], Kt f^0.62 (S/19)^(0.146 + 0.0324 log f) f(pH).

    Spreadsheet-based reference model: https://www.standard.no. The fitted variant scales
    the rate by ``A``.
    """
    fugacity = conditions.fugacity
    shear_stress = _norsok_shear_stress(conditions)
    ph = _norsok_ph(conditions)
    ph_factor = _ph_factor(conditions.temperature, ph)
    kt = _kt(conditions.temperature)
    shear_factor = (shear_stress / 19) ** (0.146 + 0.0324 * math.log10(fugacity))
    fugacity_factor = fugacity**0.62
    return coefficients["A"] * kt * fugacity_factor * shear_factor * ph_factor


def _kt(temperature):
    """Return the NORSOK temperature constant Kt, linearly interpolated in degC.

    Temperatures outside 5–150 degC take the nearest tabulated value.
    """
    pos = bisect.bisect_left(_KT_TEMPERATURES, temperature)
    if pos == 0:
        return _KT_VALUES[0]
    if pos == len(_KT_TEMPERATURES):
        return _KT_VALUES[-1]
    temp_l, temp_u = _KT_TEMPERATURES[pos - 1], _KT_TEMPERATURES[pos]
    kt_lower, kt_upper = _KT_VALUES[pos - 1], _KT_VALUES[pos]
    return kt_lower + (temperature - temp_l) * (kt_upper - kt_lower) / (temp_u - temp_l)


def _norsok_shear_stress(conditions):
    """Return the NORSOK wall shear stress [Pa] of single-phase water flow.

    The m3/day flow converts back to m3/s, and the mixture density and viscosity are
    flow-weighted as ``(rho * q) / q`` for a later multiphase extension. Both round trips and
    the area ``pi * (d / 2) ** 2`` change the last bits and are retained for the goldens.
    """
    flow_rate = units.m3day_to_m3s(conditions.water_flow_rate)
    diameter = conditions.diameter
    area = math.pi * (diameter / 2) ** 2
    velocity = flow_rate / area
    density = (conditions.water_density * flow_rate) / (flow_rate)
    viscosity = units.cp_to_pas((conditions.water_viscosity * flow_rate) / flow_rate)
    friction_factor = 0.001375 * (
        1
        + (
            20000 * conditions.roughness / diameter
            + 10**6 * viscosity / (velocity * diameter * density)
        )
        ** 0.33
    )
    return 0.5 * density * friction_factor * velocity**2


def _norsok_ph(conditions):
    """Return the NORSOK solution pH, rounded to two decimals.

    ``99.99`` marks a nonpositive hydrogen-ion root; ``_ph_factor`` then falls back to 7.
    """
    bicarb = conditions.bicarb_concentration / (1000 * _BICARBONATE_MOLAR_MASS)
    constants = _norsok_equilibrium_constants(
        conditions.temperature, conditions.pressure, conditions.ionic_strength
    )
    h_ion = _hydrogen_ion(bicarb, conditions.co2_pressure, constants)
    if h_ion > 0:
        return round(-(math.log(h_ion) / 2.3026), 2)
    return _NO_ROOT_PH


def _norsok_equilibrium_constants(temperature, pressure, ionic_strength):
    """Return the NORSOK constants ``(h0, k0, k1, k2, ksp_feco3, kw)``.

    Inputs are temperature [degC], pressure [bar] and ionic strength [g/l]; the fits use
    degF, psi and mol/l.
    """
    temp_fahrenheit = units.c_to_f(temperature)
    temp_kelvin = units.c_to_k(temperature)
    ionic = ionic_strength / _SALT_MOLAR_MASS
    pressure_psi = units.bar_to_psi(pressure)
    h0 = (14.5 / 1.00258) * 10 ** (
        -(2.27 + 0.00565 * temp_fahrenheit - 0.00000806 * temp_fahrenheit**2 + 0.075 * ionic)
    )
    k0 = 0.00258
    k1 = 387.6 * 10 ** (
        -(
            6.41
            - 0.001594 * temp_fahrenheit
            + 0.00000852 * temp_fahrenheit**2
            - 0.0000307 * pressure_psi
            - 0.4772 * ionic**0.5
            + 0.118 * ionic
        )
    )
    k2 = 10 ** (
        -(
            10.61
            - 0.00497 * temp_fahrenheit
            + 0.00001331 * temp_fahrenheit**2
            - 0.00002624 * pressure_psi
            - 1.166 * ionic**0.5
            + 0.3466 * ionic
        )
    )
    ksp_feco3 = 10 ** (-(10.13 + 0.0182 * temperature))
    kw = 10 ** (-(29.3868 - 0.0737549 * temp_kelvin + 7.47881 * 10 ** (-5) * temp_kelvin**2))
    return h0, k0, k1, k2, ksp_feco3, kw


def _hydrogen_ion(bicarb, co2_pressure, constants):
    """Solve the NORSOK charge balance for the hydrogen-ion concentration [mol/l].

    Newton's method starts at 10^-3.5 (CO2 pressure up to 20 bar) or 10^-2.9 and stops when
    a step is below 1e-6 of the current value. After 100 steps it returns the last iterate
    without a warning: decision 5 keeps replay output unchanged.
    """
    h0, k0, k1, k2, ksp_feco3, kw = constants
    denominator = h0 * k0 * k1 * k2 * co2_pressure
    if denominator == 0:
        raise PhysicsRangeError(
            f"co2_corrosion_rate NORSOK: equilibrium constants underflow at CO2 pressure = "
            f"{co2_pressure} bar; expected a temperature inside the NORSOK range"
        )
    saturation = 2 * ksp_feco3 / denominator
    h_ion = 10**-3.5 if co2_pressure <= 20 else 10**-2.9
    for iteration in itertools.count():
        residual = (
            saturation * h_ion**4
            + h_ion**3
            + bicarb * h_ion**2
            - h_ion * (k1 * k0 * h0 * co2_pressure + kw)
            - 2 * k1 * k2 * k0 * h0 * co2_pressure
        )
        slope = (
            4 * saturation * h_ion**3
            + 3 * h_ion**2
            + 2 * bicarb * h_ion
            - (k1 * k0 * h0 * co2_pressure + kw)
        )
        h_next = h_ion - residual / slope
        if abs(h_next - h_ion) < _NEWTON_TOLERANCE * h_ion or iteration >= _NEWTON_MAX_ITERATIONS:
            return h_ion
        h_ion = h_next


def _ph_factor(temperature, ph):
    """Return the NORSOK pH factor f(pH) at temperature [degC].

    NOTE(refactor): retained numerical decision. Only the exactly tabulated temperatures
    5, 15, 20, 40, 60, 80, 90, 120 and 150 degC have a pH factor, and the factor is 7 at
    every other temperature and outside pH 3.5–6.5, so the rate jumps between 40.000 and
    40.001 degC. The 5 degC first segment keeps ``2.0676 + 0.2309 pH`` where NORSOK M-506 and
    the other temperatures read ``- 0.2309``. Changing either changes goldens.
    """
    segments = _PH_FACTOR.get(temperature)
    if segments is None or not 3.5 <= ph <= 6.5:
        return 7
    return next(formula(ph) for upper, formula in segments if ph <= upper)


_RATES = {"NORSOK": _norsok_rate, "DLM": _dlm_rate, "DLD": _dld_rate}


def wall_loss(
    rates_mm_per_year: list[float] | np.ndarray, durations_s: list[float] | np.ndarray
) -> np.ndarray:
    """Integrate interval corrosion rates to cumulative wall loss.

    Parameters
    ----------
    rates_mm_per_year : array-like
        Signed interval penetration rates [mm/year].
    durations_s : array-like
        Nonnegative interval durations [s], matching the rates.

    Returns
    -------
    numpy.ndarray
        Cumulative radial wall loss [mm].

    Notes
    -----
    Reference: GEMINI WIMS corroded_mm_for_interval; piecewise-constant integration
    using a 365.25-day year.
    """
    rates = np.asarray(rates_mm_per_year, dtype=float)
    durations = np.asarray(durations_s, dtype=float)
    if rates.shape != durations.shape:
        raise PhysicsRangeError(
            f"wall_loss: rates shape = {rates.shape}; expected the durations shape "
            f"{durations.shape}"
        )
    if np.any(durations < 0):
        raise PhysicsRangeError("wall_loss: durations contain negative values; expected >= 0 s")
    return np.cumsum(rates * durations / units.SECONDS_PER_YEAR)


def remaining_wall_thickness(outer_radius: float, inner_radius: float, loss: float) -> float:
    """Predict the remaining wall using WIMS' radial wall-loss convention.

    Parameters
    ----------
    outer_radius, inner_radius : float
        Nominal outer radius and latest measured inner radius [m].
    loss : float
        Signed radial loss since the latest measurement [m].

    Returns
    -------
    float
        Remaining thickness [m], without clipping a breached wall to zero.

    Notes
    -----
    Reference: GEMINI WIMS corrosion_model.predict_remaining_thickness; outer radius
    minus the predicted inner radius. A negative loss retains the original deposition case.
    """
    return outer_radius - (inner_radius + loss)


def time_to_minimum_wall(thickness: float, minimum: float, rate: float) -> float:
    """Extrapolate time to a minimum thickness at a constant penetration rate.

    Parameters
    ----------
    thickness, minimum : float
        Current and minimum allowable wall thickness [m].
    rate : float
        Signed wall penetration speed [m/s].

    Returns
    -------
    float
        Remaining time [s]; zero at/below the threshold, infinity for nonpositive or
        nonfinite rates, and NaN for missing thickness/rate measurements.

    Notes
    -----
    Reference: GEMINI WIMS corrosion_from_logs.get_remaining_days_to_min_thickness.
    The original linear projection and special-value handling are retained in SI units.
    """
    if np.isnan(thickness) or np.isnan(rate):
        return float("nan")
    if thickness <= minimum:
        return 0.0
    if rate <= 0 or not np.isfinite(rate):
        return float("inf")
    return (thickness - minimum) / rate
