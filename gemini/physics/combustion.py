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

    Validity: fuel, electric_capacity nonnegative; load and thermal_efficiency in [0, 1]; the
    electric output must not exceed the fuel minus the recovered heat, or the heat loss is negative.
    No division occurs.
    Source: Constant thermal efficiency is a manufacturer-data convention; the rest is a first-law
    balance, and no published source is needed.
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

    Validity: gas_flow nonnegative; co2_fraction and methane_fraction in [0, 1] with a sum of at
    most one; combustion_efficiency in [0, 1]; heating_value positive. No division occurs.
    Source: Destruction efficiency from US EPA AP-42, section 13.5 and heating value from the NIST
    Chemistry WebBook, as cited for FLARE_EFFICIENCY and METHANE_HEATING_VALUE; the balance is
    stoichiometry.
    """
    methane = methane_fraction * gas_flow
    burnt = combustion_efficiency * methane
    co2 = co2_fraction * gas_flow + burnt * constants.CO2_MOLAR_MASS / METHANE_MOLAR_MASS
    return co2, methane - burnt, burnt * heating_value


@ops.physics
def released_heat(gas_flow: float, heating_value: float, combustion_efficiency: float) -> float:
    """Return the heat [W] that burning ``gas_flow`` [kg/s] of a gas of ``heating_value`` releases.

    Source: definition of the lower heating value; ``combustion_efficiency`` is the share burnt.
    """
    return gas_flow * heating_value * combustion_efficiency


def burnt_gas_emissions(
    gas_flow: float,
    carried_co2: float,
    formed_co2: float,
    methane_fraction: float,
    combustion_efficiency: float,
) -> tuple:
    """Return the CO2 and methane emissions of a gas of known composition burnt in a flare.

    Parameters
    ----------
    gas_flow : float
        Gas mass flow [kg/s].
    carried_co2 : float
        Mass fraction of CO2 in the gas [-].
    formed_co2 : float
        CO2 that complete combustion forms per kilogram of gas [-].
    methane_fraction : float
        Mass fraction of methane in the gas [-].
    combustion_efficiency : float
        Share of the combustible gas burnt [-].

    Returns
    -------
    tuple of float
        ``(CO2, CH4)`` [kg/s]: ``m (x_CO2 + eta f_CO2)`` and ``m x_CH4 (1 - eta)``.

    Notes
    -----
    The composition form of ``flare_emissions``, for every species of ``gas.SPECIES``.

    Validity: gas_flow nonnegative; fractions in [0, 1]; combustion_efficiency in [0, 1].
    Source: Destruction efficiency from US EPA AP-42, section 13.5, as cited for FLARE_EFFICIENCY;
    the balance is stoichiometry.
    """
    co2 = gas_flow * (carried_co2 + combustion_efficiency * formed_co2)
    return co2, gas_flow * methane_fraction * (1 - combustion_efficiency)


@ops.physics
def fuel_power(gas_flow: float, heating_value: float) -> float:
    """Return the fuel power [W] of a gas flow, ``F = m LHV``.

    Parameters
    ----------
    gas_flow : float
        Gas mass flow [kg/s].
    heating_value : float
        Lower heating value [J/kg].

    Returns
    -------
    float
        Fuel power on the lower heating value [W].

    Notes
    -----
    Definition of a heating value.

    Validity: Any real inputs. No division occurs.
    Source: Definition of a heating value; no published source is needed.
    """
    return gas_flow * heating_value


@ops.physics
def covered_load(load: float, need: float, available: float) -> float:
    """Return the load [-] an engine reaches on the fuel available, ``L min(1, F_a / F_n)``.

    Parameters
    ----------
    load : float
        Commanded load [-].
    need : float
        Fuel power that load needs [W], nonnegative.
    available : float
        Fuel power available [W], nonnegative.

    Returns
    -------
    float
        The load scaled by the share of the need that is covered; the commanded load at no need.

    Notes
    -----
    Validity: Nonnegative inputs; with a no-load fuel fraction the result is slightly above the
    load of the Willans line, and ``CHP`` takes the smaller fuel.
    Source: A plain energy balance; no published source is needed.
    """
    share = ops.where(need > 0, ops.minimum(1.0, ops.truediv(available, need)), 1.0)
    return load * share


@ops.physics
def fuel_split(need: float, available: float, heating_value: float) -> tuple:
    """Return how a burner covers a fuel need: co-produced gas first, the grid for the rest.

    Parameters
    ----------
    need : float
        Fuel power the burner needs [W], nonnegative.
    available : float
        Fuel power of the co-produced gas that reaches it [W], nonnegative.
    heating_value : float
        Lower heating value of the co-produced gas [J/kg]; zero for a gas that does not burn.

    Returns
    -------
    tuple of float
        ``(coproduced, purchased, burnt)``: the co-produced ``min(need, available)`` and the
        purchased ``need - coproduced`` [W], and the co-produced gas burnt [kg/s].

    Notes
    -----
    Validity: Nonnegative inputs. Source: The dispatch rule of the challenge model; a plain energy
    balance, no published source is needed.
    """
    coproduced = ops.minimum(need, available)
    burnt = ops.where(heating_value > 0, ops.truediv(coproduced, heating_value), 0.0)
    return coproduced, need - coproduced, burnt


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
