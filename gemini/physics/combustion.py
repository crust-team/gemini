"""Fuel-fired heat and power: fuel input of a boiler or engine, flare emissions."""

from gemini import ops
from gemini.ops import Constant
from gemini.physics import constants

METHANE_MOLAR_MASS = Constant(
    "METHANE_MOLAR_MASS",
    0.016043,
    "kg/mol",
    "molar mass of methane (IUPAC 2013 standard atomic weights)",
)

METHANE_HEATING_VALUE = 50.0e6
"""Lower heating value of methane [J/kg]: 802.3 kJ/mol (NIST Chemistry WebBook) / 16.043 g/mol."""

FLARE_EFFICIENCY = 0.98
"""Combustion (destruction) efficiency of a well-operated flare [-] (US EPA AP-42, 13.5)."""


@ops.physics
def willans_fuel_input(
    load: float, electric_capacity: float, electric_efficiency: float, no_load_fraction: float
) -> float:
    """Return the fuel power of an engine on its Willans line; zero when the engine is off.

    Parameters
    ----------
    load : float
        Electric output as a fraction of the capacity [-], in [0, 1].
    electric_capacity : float
        Rated electric output [W].
    electric_efficiency : float
        Electric efficiency at full load on the lower heating value [-], positive.
    no_load_fraction : float
        Fuel at no load as a fraction of the full-load fuel [-], in [0, 1).

    Returns
    -------
    float
        ``F = F_full (f0 + (1 - f0) L)`` [W] with ``F_full = capacity / efficiency``, and 0 at
        ``L = 0``.

    Notes
    -----
    Reference: Heywood (1988), Internal Combustion Engine Fundamentals: fuel flow at constant
    speed is close to linear in brake load.
    """
    share = no_load_fraction + (1 - no_load_fraction) * load
    return ops.where(load != 0, share * electric_capacity / electric_efficiency, 0.0)


@ops.physics
def engine_energy_flows(
    fuel: float, load: float, electric_capacity: float, thermal_efficiency: float
) -> tuple:
    """Return the recoverable engine heat and the electric output of a combined heat and power unit.

    Parameters
    ----------
    fuel : float
        Fuel power on the lower heating value [W].
    load : float
        Electric output as a fraction of the capacity [-].
    electric_capacity : float
        Rated electric output [W].
    thermal_efficiency : float
        Recoverable heat (jacket water, oil, exhaust) over the fuel [-].

    Returns
    -------
    tuple of float
        ``(thermal_efficiency * F, L * capacity)`` [W]. What is not recovered or generated is
        the heat loss, ``F - P - Q``.

    Notes
    -----
    Constant thermal efficiency on the fuel basis (manufacturer data of gas engines).
    """
    return thermal_efficiency * fuel, load * electric_capacity


@ops.physics
def flare_emissions(
    gas_flow: float,
    co2_fraction: float,
    methane_fraction: float,
    combustion_efficiency: float,
    heating_value: float,
) -> tuple:
    """Return the CO2 and methane emissions and the fuel power of a flared gas.

    Parameters
    ----------
    gas_flow : float
        Gas mass flow [kg/s].
    co2_fraction, methane_fraction : float
        Mass fractions of CO2 and of the combustible part, taken as methane [-].
    combustion_efficiency : float
        Share of the methane burnt [-]; 0 for a vent.
    heating_value : float
        Lower heating value of the combustible part [J/kg].

    Returns
    -------
    tuple of float
        ``(CO2, CH4, fuel)``: with ``m_b = efficiency * x_CH4 * m_dot``, CO2 emission
        ``x_CO2 m_dot + m_b M_CO2 / M_CH4`` [kg/s], methane emission ``x_CH4 m_dot - m_b``
        [kg/s] and fuel ``m_b * heating_value`` [W], the chemical energy of the burnt gas.

    Notes
    -----
    Stoichiometry CH4 + 2 O2 -> CO2 + 2 H2O; destruction efficiency from US EPA AP-42, section
    13.5 "Industrial Flares"; heating value from the NIST Chemistry WebBook. Other combustibles
    and H2S are not modelled.
    """
    methane = methane_fraction * gas_flow
    burnt = combustion_efficiency * methane
    co2 = co2_fraction * gas_flow + burnt * constants.CO2_MOLAR_MASS / METHANE_MOLAR_MASS
    return co2, methane - burnt, burnt * heating_value


@ops.physics
def emission_rate(
    fuel: float, fuel_factor: float, grid_electricity: float, electricity_factor: float
) -> float:
    """Return the CO2 emission rate [kg/s]: ``fuel * f_fuel + P_grid * f_electricity``.

    Parameters
    ----------
    fuel, grid_electricity : float
        Fuel input and electricity taken from the grid, both powers [W].
    fuel_factor, electricity_factor : float
        Emission factors [kg/J] of the fuel and of the grid.

    Returns
    -------
    float
        Emission rate [kg/s].

    Notes
    -----
    Direct and purchased-electricity emissions with factors the user gives, the Scope 1 and 2 sum
    of the GHG Protocol Corporate Standard (2004); valid for nonnegative inputs.
    """
    return fuel * fuel_factor + grid_electricity * electricity_factor
