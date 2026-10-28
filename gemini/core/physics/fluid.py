"""Constant fluid properties inherited from GEMINI's PVTConstantSTP model."""

from typing import Callable

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


class ConstantWater:
    """Constant PVT model with the original uppercase override keys."""

    def __init__(self, **overrides: float):
        """Validate legacy RHOL, VISL, etc. overrides, all in SI units."""
        names = dict(
            RHOL="rho_l",
            RHOG="rho_g",
            GMF="gmf",
            VISL="mu_l",
            VISG="mu_g",
            CPL="cp_l",
            CPG="cp_g",
            TCL="k_l",
            TCG="k_g",
            SIGMA="sigma",
        )
        # These original metadata fields never affected get_pvt's returned values.
        metadata = {
            "HG",
            "HL",
            "SG",
            "SL",
            "pressure_max",
            "pressure_min",
            "temperature_max",
            "temperature_min",
        }
        unknown = set(overrides) - names.keys() - metadata
        if unknown:
            raise ValueError(f"Unknown constant-water properties: {sorted(unknown)}")
        self._properties = FluidProperties(
            **{names[k]: v for k, v in overrides.items() if k in names}
        )

    def properties(self, p: float, T: float) -> FluidProperties:
        """Return constant properties for pressure [Pa] and temperature [K]."""
        return self._properties


_FLUIDS = {"brine": ConstantWater, "water": ConstantWater}


def get_fluid(name: str = "brine", **overrides: float) -> ConstantWater:
    """Resolve a configured fluid name to a property model.

    Parameters
    ----------
    name : str
        Registered fluid name [-]; water and brine default to ConstantWater.
    **overrides : float
        Original uppercase PVT property keys in SI units, e.g. RHOL [kg/m3].

    Returns
    -------
    ConstantWater
        Property model exposing properties(p [Pa], T [K]).

    Notes
    -----
    Reference: GEMINI PVTConstantSTP defaults; factory selection happens during
    configuration and does not modify properties during a calculation.
    """
    try:
        factory = _FLUIDS[name]
    except KeyError as exc:
        raise ValueError(f"Unknown fluid {name!r}; available: {sorted(_FLUIDS)}") from exc
    return factory(**overrides)


def register_fluid(name: str, factory: Callable[..., ConstantWater]) -> None:
    """Configure a named fluid factory before constructing a plant.

    Parameters
    ----------
    name : str
        New fluid model identifier [-]; default water and brine cannot be replaced.
    factory : callable
        Factory accepting SI property overrides and returning a ConstantWater model.

    Returns
    -------
    None
        The model is available to get_fluid and Stream.volumetric_flow.

    Notes
    -----
    Reference: Configuration-only registration for consistent density across component ports.
    Physics calculations do not register or mutate models.
    """
    if name in {"water", "brine"}:
        raise ValueError(f"Cannot replace default fluid {name!r}")
    model = factory()
    if not isinstance(model.properties(100000, 300), FluidProperties):
        raise TypeError("A fluid factory must return a model producing FluidProperties")
    _FLUIDS[name] = factory
