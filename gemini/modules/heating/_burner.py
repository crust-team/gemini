"""What a gas burner does with its fuel stream: co-produced gas first, the grid for the rest."""

from gemini import ops
from gemini.physics import combustion, gas
from gemini.types.fluid import FLUE_CO2


def available_fuel(fuel):
    """Return the fuel power [W] of the gas in the stream ``fuel``."""
    return combustion.fuel_power(fuel.m_dot, fuel.fluid.heating_value())


def has_grid(fuel):
    """Return whether a burner on the stream ``fuel`` may draw grid gas."""
    return fuel.fluid.grid_composition is not None


def fuel_split(need, fuel):
    """Return ``(coproduced, purchased, burnt)`` of a burner with fuel need ``need`` [W]."""
    return combustion.fuel_split(need, available_fuel(fuel), fuel.fluid.heating_value())


def burned_stream(need, fuel):
    """Return what a burner with fuel need ``need`` [W] takes through its drawn ``fuel_in``.

    The flow is the co-produced gas it burns and, in kg/s of grid gas, what it buys.
    """
    _, purchased, burnt = fuel_split(need, fuel)
    return fuel.with_(m_dot=burnt + _grid_mass(purchased, fuel))


def _grid_mass(purchased, fuel):
    """Return the grid gas [kg/s] of a purchased fuel power [W]; zero on a stream without a grid."""
    if not has_grid(fuel):
        return 0.0
    return ops.truediv(purchased, gas.lower_heating_value(fuel.fluid.grid_composition))


def _grid_factor(fuel):
    """Return the CO2 [kg/J] of the grid gas of a stream; zero on a stream without a grid."""
    return gas.emission_per_energy(fuel.fluid.grid_composition) if has_grid(fuel) else 0


def flue_stream(need, fuel):
    """Return the flue of a burner: the CO2 of everything burned, formed and carried in the gas."""
    coproduced, purchased, _ = fuel_split(need, fuel)
    released = combustion.emission_rate(
        coproduced, fuel.fluid.emission_factor(), purchased, _grid_factor(fuel)
    )
    return fuel.with_(m_dot=released, fluid=FLUE_CO2)
