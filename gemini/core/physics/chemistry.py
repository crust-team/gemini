"""Henry-law CO2 partition model retained from GEMINI water-analysis workflows."""

import math

from . import units


def henry_constant(T: float) -> float:
    """Return the temperature-dependent Henry solubility constant.

    Parameters
    ----------
    T : float
        Temperature [K].

    Returns
    -------
    float
        Solubility coefficient [mol/m3/Pa].

    Notes
    -----
    Reference: GEMINI co2_partial_pressure_model.henry_constant; 0.0385 mol/l/bar
    at 293.15 K, with the original 2400 K exponential temperature coefficient.
    """
    return units.mol_l_bar_to_mol_m3_pa(0.0385 * math.exp(2400 * (1 / T - 1 / 293.15)))


def co2_solubility_liquid(co2_fraction: float, temperature: float, pressure: float) -> float:
    """Evaluate dissolved CO2 using Henry's law.

    Parameters
    ----------
    co2_fraction : float
        Gas-phase mole fraction [-].
    temperature, pressure : float
        Sample temperature [K] and absolute pressure [Pa].

    Returns
    -------
    float
        Dissolved CO2 per liquid volume [mol/m3].

    Notes
    -----
    Reference: GEMINI co2_partial_pressure_model; concentration equals partial
    pressure times the Henry solubility coefficient.
    """
    return co2_fraction * henry_constant(temperature) * pressure


def co2_solubility_gas(
    co2_fraction: float, gas_water_ratio: float, gas_density: float, gas_molecular_weight: float
) -> float:
    """Evaluate CO2 contained in the gas per unit water volume.

    Parameters
    ----------
    co2_fraction, gas_water_ratio : float
        Mole fraction and standard gas/water volume ratio [-].
    gas_density, gas_molecular_weight : float
        Standard gas density [kg/m3] and molar mass [kg/mol].

    Returns
    -------
    float
        Gas-phase CO2 per liquid volume [mol/m3].

    Notes
    -----
    Reference: GEMINI co2_partial_pressure_model; phase mole balance.
    """
    return co2_fraction * gas_water_ratio * gas_density / gas_molecular_weight


def co2_partial_pressure(
    *,
    co2_fraction: float,
    gas_pressure: float,
    gas_water_ratio: float,
    gas_density: float,
    gas_molecular_weight: float,
    temperature_sample: float,
    temperature_system: float
) -> float:
    """Return CO2 partial pressure [Pa] from SI sample and system conditions.

    Parameters
    ----------
    co2_fraction, gas_water_ratio : float
        Mole fraction and standard gas/water volume ratio [-].
    gas_pressure, gas_density, gas_molecular_weight : float
        Sample pressure [Pa], density [kg/m3], molar mass [kg/mol].
    temperature_sample, temperature_system : float
        Sample and system temperatures [K].

    Returns
    -------
    float
        Equilibrated CO2 partial pressure [Pa].

    Notes
    -----
    Reference: GEMINI co2_partial_pressure_model; total sampled gas plus dissolved
    CO2 is repartitioned using Henry's law at the system temperature.
    """
    total = co2_solubility_liquid(co2_fraction, temperature_sample, gas_pressure)
    total += co2_solubility_gas(co2_fraction, gas_water_ratio, gas_density, gas_molecular_weight)
    return total / henry_constant(temperature_system)
