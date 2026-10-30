"""What a gas burner does with its fuel stream: co-produced gas first, the grid for the rest."""

from gemini import ops
from gemini.physics import combustion, gas


def available_fuel(fuel):
    """Return the fuel power [W] of the gas in the stream ``fuel``."""
    return combustion.fuel_power(fuel.m_dot, fuel.fluid.heating_value())


def has_grid(fuel):
    """Return whether a burner on the stream ``fuel`` may draw grid gas."""
    return fuel.fluid.grid_composition is not None


def fuel_split(need, fuel):
    """Return ``(coproduced, purchased, burnt)`` of a burner with fuel need ``need`` [W]."""
    return combustion.fuel_split(need, available_fuel(fuel), fuel.fluid.heating_value())


def unburned_gas(need, fuel):
    """Return the stream ``fuel`` less the gas a burner with fuel need ``need`` burns."""
    _, _, burnt = fuel_split(need, fuel)
    return fuel.with_(m_dot=ops.maximum(fuel.m_dot - burnt, 0.0))


def _grid_factor(fuel):
    """Return the CO2 [kg/J] of the grid gas of a stream; zero on a stream without a grid."""
    return gas.emission_per_energy(fuel.fluid.grid_composition) if has_grid(fuel) else 0


def fuel_outputs(need, fuel):
    """Return the outputs a burner with fuel need ``need`` [W] reports."""
    coproduced, purchased, burnt = fuel_split(need, fuel)
    return {
        "fuel_coproduced": coproduced,
        "fuel_purchased": purchased,
        "burned_mass_flow": burnt,
        "co2_emission": combustion.emission_rate(
            coproduced, fuel.fluid.emission_factor(), purchased, _grid_factor(fuel)
        ),
    }
