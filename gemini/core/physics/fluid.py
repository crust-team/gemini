"""Constant fluid properties inherited from GEMINI's PVTConstantSTP model.

The defaults are the original constant-water values; pressure and temperature do not change
them. ``gemini.core.types.Fluid`` builds and caches one snapshot per fluid.
"""

from pydantic import BaseModel, ConfigDict, Field


class FluidProperties(BaseModel):
    """Immutable liquid/gas property snapshot in SI units."""

    model_config = ConfigDict(frozen=True)
    rho_l: float = Field(1000, gt=0, description="Liquid density [kg/m3]")
    rho_g: float = Field(1.976, gt=0, description="Gas density [kg/m3]")
    gmf: float = Field(0, ge=0, lt=1, description="Gas mass fraction [-]")
    mu_l: float = Field(0.001, gt=0, description="Liquid viscosity [Pa s]")
    mu_g: float = Field(21.29e-6, gt=0, description="Gas viscosity [Pa s]")
    cp_l: float = Field(4217.4, gt=0, description="Liquid heat capacity [J/kg/K]")
    cp_g: float = Field(819, gt=0, description="Gas heat capacity [J/kg/K]")
    k_l: float = Field(1.6, gt=0, description="Liquid thermal conductivity [W/m/K]")
    k_g: float = Field(0.0147, gt=0, description="Gas thermal conductivity [W/m/K]")
    sigma: float = Field(0.0728, gt=0, description="Surface tension [N/m]")

    @property
    def density(self) -> float:
        """Return homogeneous mixture density [kg/m3]."""
        return 1 / (self.gmf / self.rho_g + (1 - self.gmf) / self.rho_l)
