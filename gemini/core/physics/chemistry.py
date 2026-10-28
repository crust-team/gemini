"""Henry-law CO2 partition model retained from GEMINI water-analysis workflows."""

import math


def henry_constant(T: float) -> float:
    """Return Henry constant [mol/m3/Pa] at temperature [K]."""
    return 0.0385 * math.exp(2400 * (1 / T - 1 / 293.15)) * 0.01


def co2_solubility_liquid(co2_fraction: float, temperature: float, pressure: float) -> float:
    """Return dissolved CO2 [mol/m3] from fraction [-], temperature [K], pressure [Pa]."""
    return co2_fraction * henry_constant(temperature) * pressure


def co2_solubility_gas(
    co2_fraction: float, gas_water_ratio: float, gas_density: float, gas_molecular_weight: float
) -> float:
    """Return gas CO2 [mol/m3] from fraction [-], GWR [-], density [kg/m3], mass [kg/mol]."""
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
    """
    total = co2_solubility_liquid(co2_fraction, temperature_sample, gas_pressure)
    total += co2_solubility_gas(co2_fraction, gas_water_ratio, gas_density, gas_molecular_weight)
    return total / henry_constant(temperature_system)
