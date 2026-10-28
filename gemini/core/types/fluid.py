"""Immutable stream composition and cached constant-property models."""

from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from gemini.core.physics.fluid import ConstantWater, FluidProperties
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
    """Stream dtype; composition is descriptive unless the property model uses it.

    Salinity, CO2 and free gas are mass fractions. Glycol is a volume fraction,
    matching the cited manufacturer table. Constant STP does not infer brine
    density or viscosity from salt concentration; supply measured overrides.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)
    kind: Literal["brine", "water", "glycol_water"] = "brine"
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
        return _property_model(self).properties(p, T)


@lru_cache(maxsize=256)
def _property_model(fluid: Fluid) -> ConstantWater:
    values = {"GMF": fluid.gas_mass_fraction}
    if fluid.kind == "glycol_water":
        # NOTE(refactor): DOWFROST HD, 30% propylene glycol by volume at 40 C.
        # Frozen reference values, not a temperature-dependent glycol correlation.
        # https://www.dow.com/content/dam/dcc/documents/en-us/productdatasheet/180/
        # 180-01315-01-dowfrost-hd-tds.pdf (table, page 3).
        values.update(RHOL=1029.85, CPL=3841, TCL=0.4622, VISL=0.0016295)
    for field, key in (
        ("liquid_density", "RHOL"),
        ("liquid_viscosity", "VISL"),
        ("specific_heat", "CPL"),
        ("thermal_conductivity", "TCL"),
    ):
        value = getattr(fluid, field)
        if value is not None:
            values[key] = value
    return ConstantWater(**values)


BRINE = Fluid()
WATER = Fluid(kind="water")
GLYCOL_30 = Fluid(kind="glycol_water", glycol_fraction=0.3)
