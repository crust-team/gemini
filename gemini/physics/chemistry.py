"""Henry-law CO2 partition model retained from GEMINI water-analysis workflows."""

from gemini import ops

from . import units


@ops.physics
def henry_constant(temperature: float) -> float:
    """Return the temperature-dependent Henry solubility constant.

    Parameters
    ----------
    temperature : float
        Temperature [K].

    Returns
    -------
    float
        Solubility coefficient [mol/m3/Pa].

    Notes
    -----
    K_H = 0.0385 exp(2400 (1 / T - 1 / 293.15)) in mol/l/bar, converted to mol/m3/Pa. The value
    0.0385 mol/l/bar at 293.15 K and the 2400 K temperature coefficient are the retained GEMINI
    water-analysis values (co2_partial_pressure_model.henry_constant), not a published fit;
    the exponential is a van 't Hoff form with a constant enthalpy of solution.

    Validity: T must be positive (the code divides by T). The coefficients are anchored at 293.15 K;
    no wider range of the fit is established in the code base.
    """
    return units.mol_l_bar_to_mol_m3_pa(0.0385 * ops.exp(2400 * (1 / temperature - 1 / 293.15)))


@ops.physics
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
    c = y p K_H(T): the dissolved concentration equals the partial pressure of CO2 (mole
    fraction times total pressure) times the Henry solubility coefficient. Retained GEMINI
    water-analysis formulation (co2_partial_pressure_model); valid where ``henry_constant`` is.
    """
    return co2_fraction * henry_constant(temperature) * pressure


@ops.physics
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
    c = y GWR rho_gas / M_gas: moles of CO2 in the standard gas volume per unit volume of
    water. Retained GEMINI water-analysis formulation (co2_partial_pressure_model); valid for
    an ideal gas phase at standard conditions.
    """
    return co2_fraction * gas_water_ratio * gas_density / gas_molecular_weight


@ops.physics
def co2_partial_pressure(
    *,
    co2_fraction: float,
    gas_pressure: float,
    gas_water_ratio: float,
    gas_density: float,
    gas_molecular_weight: float,
    temperature_sample: float,
    temperature_system: float,
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
    p = (c_liquid + c_gas) / K_H(T_system), with c_liquid from ``co2_solubility_liquid`` at the
    sample conditions and c_gas from ``co2_solubility_gas``: total sampled gas plus dissolved
    CO2 is repartitioned using Henry's law at the system temperature. Retained GEMINI
    water-analysis formulation (co2_partial_pressure_model).

    Validity: Both temperatures must be positive and gas_molecular_weight positive; co2_fraction is
    in [0, 1] and gas_pressure, gas_water_ratio and gas_density are nonnegative. Ideal-gas, dilute-
    solution Henry law only.
    """
    total = co2_solubility_liquid(co2_fraction, temperature_sample, gas_pressure)
    total += co2_solubility_gas(co2_fraction, gas_water_ratio, gas_density, gas_molecular_weight)
    return total / henry_constant(temperature_system)
