"""Immutable stream composition and cached constant-property models."""

from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from gemini.core.physics import constants
from gemini.core.physics.chemistry import henry_constant
from gemini.core.physics.fluid import FluidProperties
from gemini.core.types.quantities import (
    Density,
    Fraction,
    Pressure,
    SpecificHeat,
    Temperature,
    ThermalConductivity,
    Viscosity,
)


class Fluid(BaseModel):
    """Stream fluid; composition is descriptive unless the property model uses it.

    Salinity, CO2 and free gas are mass fractions. Glycol is a volume fraction,
    matching the cited manufacturer table. Constant STP does not infer brine
    density or viscosity from salt concentration; supply measured overrides.

    ``steam`` marks water vapour, such as the gas outlet of a flash ``Separator``. Its
    constant property snapshot is the liquid-water default and does not describe vapour:
    steam equipment takes enthalpy and entropy from ``gemini.core.physics.steam`` instead, so
    do not convert a steam stream's volume flow or audit its latent heat with ``cp_l * T``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)
    kind: Literal["brine", "water", "glycol_water", "steam"] = "brine"
    salinity: Fraction = 0.0
    co2_mass_fraction: Fraction = 0.0
    gas_mass_fraction: Fraction = Field(0, lt=1)
    glycol_fraction: Fraction = 0.0
    property_model: Literal["constant_stp"] = "constant_stp"
    liquid_density: Density | None = None
    liquid_viscosity: Viscosity | None = None
    specific_heat: SpecificHeat | None = None
    thermal_conductivity: ThermalConductivity | None = None

    @model_validator(mode="after")
    def composition(self):
        """Reject impossible compositions and unsupported glycol concentrations."""
        if self.salinity + self.co2_mass_fraction + self.gas_mass_fraction > 1:
            raise ValueError("Mass fractions must sum to at most one")
        if self.kind != "glycol_water" and self.glycol_fraction:
            raise ValueError("Glycol fraction requires glycol_water")
        if self.kind == "glycol_water" and self.glycol_fraction != 0.3:
            raise ValueError("constant_stp currently supports only 30% glycol by volume")
        return self

    def properties(self, p: Pressure, T: Temperature) -> FluidProperties:
        """Return cached constant SI properties; pressure and temperature are independent."""
        return _properties(self)

    def corrosion_inputs(self, p: Pressure, T: Temperature) -> dict[str, float]:
        """Convert dissolved CO2 and salt mass fractions for the existing corrosion boundary.

        The Henry-law approximation is evaluated at the inlet temperature. Explicit
        measured gas mole fraction/partial pressure should override it when available.

        NOTE(refactor): dissolved mass fraction is NOT a gas mole fraction. It converts from
        kg/m3 to mol/m3 with the CO2 molar mass, then inverts the existing Henry law.
        """
        rho = self.properties(p, T).rho_l
        dissolved_co2 = self.co2_mass_fraction * rho / constants.CO2_MOLAR_MASS
        return {
            "co2_partial_pressure": dissolved_co2 / henry_constant(T),
            "ionic_strength": self.salinity * rho,
        }


_GLYCOL_30_PROPERTIES = dict(rho_l=1029.85, cp_l=3841, k_l=0.4622, mu_l=0.0016295)

_OVERRIDES = (
    ("liquid_density", "rho_l"),
    ("liquid_viscosity", "mu_l"),
    ("specific_heat", "cp_l"),
    ("thermal_conductivity", "k_l"),
)


@lru_cache(maxsize=256)
def _properties(fluid: Fluid) -> FluidProperties:
    """Return the constant property snapshot of a fluid, cached by its complete value.

    NOTE(refactor): ``glycol_water`` uses DOWFROST HD reference values for 30% propylene
    glycol by volume at 40 C, frozen rather than a temperature-dependent glycol correlation:
    https://www.dow.com/content/dam/dcc/documents/en-us/productdatasheet/180/
    180-01315-01-dowfrost-hd-tds.pdf (table, page 3).
    """
    values = {"gmf": fluid.gas_mass_fraction}
    if fluid.kind == "glycol_water":
        values.update(_GLYCOL_30_PROPERTIES)
    for field, name in _OVERRIDES:
        value = getattr(fluid, field)
        if value is not None:
            values[name] = value
    return FluidProperties(**values)


BRINE = Fluid()
WATER = Fluid(kind="water")
GLYCOL_30 = Fluid(kind="glycol_water", glycol_fraction=0.3)
STEAM = Fluid(kind="steam")
