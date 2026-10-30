"""Constant fluid properties inherited from GEMINI's PVTConstantSTP model.

The defaults are the original constant-water values; pressure and temperature do not change
them. ``gemini.types.Fluid`` builds and caches one snapshot per fluid.

``mixture_density``, ``volume_flow``, ``liquid_volume_flow`` and ``heat_capacity_rate`` carry no
``@ops.physics``: ``Stream`` and ``FluidProperties`` call them on every eager step, the decorator
would make those calls about 3.5 times slower, and they divide only by validated positive
properties, so they need no eager scope.
"""

from dataclasses import dataclass, fields

from gemini.errors import PhysicsRangeError

DEFAULT_LIQUID_DENSITY = 1000.0
"""Density [kg/m3] of the constant-water liquid of GEMINI's PVTConstantSTP model, near 4 degC."""


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

    rho_l: float = DEFAULT_LIQUID_DENSITY
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

    @property
    def liquid_volumetric_heat_capacity(self) -> float:
        """Return the liquid volumetric heat capacity rho_l * cp_l [J/m3/K]."""
        return self.rho_l * self.cp_l


def mixture_density(liquid_density: float, gas_density: float, gas_mass_fraction: float) -> float:
    """Return the homogeneous mixture density [kg/m3] of a gas mass fraction [-].

    Parameters
    ----------
    liquid_density, gas_density : float
        Phase densities [kg/m3], positive.
    gas_mass_fraction : float
        Gas mass fraction ``x`` [-], in ``[0, 1]``.

    Returns
    -------
    float
        Mixture density [kg/m3], ``1 / (x / rho_g + (1 - x) / rho_l)``.

    Notes
    -----
    No-slip (homogeneous) mixture: the specific volumes of the phases add. Valid for any
    mixture whose phases move at one velocity. Reference: the specific volume of a mixture is
    the mass-weighted sum of the phase specific volumes (Collier and Thome, Convective Boiling
    and Condensation, 3rd ed., 1994, homogeneous model).
    """
    return 1 / (gas_mass_fraction / gas_density + (1 - gas_mass_fraction) / liquid_density)


def volume_flow(mass_flow: float, density: float) -> float:
    """Return the volume flow [m3/s] of a mass flow at a density, ``q = m / rho``.

    Parameters
    ----------
    mass_flow : float
        Signed mass flow [kg/s].
    density : float
        Density [kg/m3], nonzero.

    Returns
    -------
    float
        Signed volume flow [m3/s].

    Notes
    -----
    Definition of density. Use the mixture density for the mixture volume flow and a phase
    density for the volume flow of that phase.
    """
    return mass_flow / density


def liquid_volume_flow(mass_flow: float, gas_mass_fraction: float, liquid_density: float) -> float:
    """Return the liquid volume flow [m3/s] of a mixture, ``q_l = m (1 - x) / rho_l``.

    Parameters
    ----------
    mass_flow : float
        Signed mixture mass flow [kg/s].
    gas_mass_fraction : float
        Gas mass fraction ``x`` [-], in ``[0, 1]``.
    liquid_density : float
        Liquid density [kg/m3], nonzero.

    Returns
    -------
    float
        Signed liquid volume flow [m3/s].

    Notes
    -----
    The liquid mass flow is ``m (1 - x)``; its volume follows from the liquid density.

    Source: A plain mass balance of the liquid fraction; no published source is needed.
    """
    return mass_flow * (1 - gas_mass_fraction) / liquid_density


def heat_capacity_rate(mass_flow: float, heat_capacity: float) -> float:
    """Return the heat capacity rate [W/K] of a stream, ``C = m cp``.

    Parameters
    ----------
    mass_flow : float
        Signed mass flow [kg/s].
    heat_capacity : float
        Specific heat capacity [J/kg/K].

    Returns
    -------
    float
        Heat capacity rate [W/K], the energy flow per kelvin of temperature change.

    Notes
    -----
    Reference: Incropera and DeWitt, Fundamentals of Heat and Mass Transfer, the capacity
    rate ``C = m cp`` of the effectiveness-NTU method.

    Validity: Valid for any real mass flow and heat capacity; the effectiveness-NTU relations need a
    positive rate, a negative one only marks a reversed stream. No division occurs.
    """
    return mass_flow * heat_capacity
