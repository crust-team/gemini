"""Constant fluid properties inherited from GEMINI's PVTConstantSTP model.

The defaults are the original constant-water values; pressure and temperature do not change
them. ``gemini.core.types.Fluid`` builds and caches one snapshot per fluid.
"""

from dataclasses import dataclass, fields

from gemini.errors import PhysicsRangeError


@dataclass(frozen=True, slots=True)
class FluidProperties:
    """Immutable liquid/gas property snapshot in SI units.

    Every field is converted to ``float``. Densities, viscosities, heat capacities,
    conductivities and surface tension must be positive; the gas mass fraction lies in
    ``[0, 1)``. A violation raises ``PhysicsRangeError``.

    Fields: ``rho_l`` and ``rho_g`` densities [kg/m3], ``gmf`` gas mass fraction [-], ``mu_l`` and
    ``mu_g`` viscosities [Pa s], ``cp_l`` and ``cp_g`` heat capacities [J/kg/K], ``k_l`` and
    ``k_g`` conductivities [W/m/K], ``sigma`` surface tension [N/m].
    """

    rho_l: float = 1000.0
    rho_g: float = 1.976
    gmf: float = 0.0
    mu_l: float = 0.001
    mu_g: float = 21.29e-6
    cp_l: float = 4217.4
    cp_g: float = 819.0
    k_l: float = 1.6
    k_g: float = 0.0147
    sigma: float = 0.0728

    def __post_init__(self):
        """Convert the fields to ``float`` and enforce the physical bounds."""
        for field in fields(self):
            value = float(getattr(self, field.name))
            object.__setattr__(self, field.name, value)
            valid = 0 <= value < 1 if field.name == "gmf" else value > 0
            if not valid:
                expected = "0 <= gmf < 1" if field.name == "gmf" else f"{field.name} > 0"
                raise PhysicsRangeError(
                    f"FluidProperties: {field.name} = {value}; expected {expected}"
                )

    @property
    def density(self) -> float:
        """Return homogeneous mixture density [kg/m3]."""
        return mixture_density(self.rho_l, self.rho_g, self.gmf)


def mixture_density(liquid_density, gas_density, gas_mass_fraction):
    """Return the homogeneous mixture density [kg/m3] of a gas mass fraction [-].

    ``1 / (gmf / rho_g + (1 - gmf) / rho_l)``; the operands may be floats, arrays or traced
    values.
    """
    return 1 / (gas_mass_fraction / gas_density + (1 - gas_mass_fraction) / liquid_density)
