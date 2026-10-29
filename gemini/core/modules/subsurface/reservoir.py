"""Production and injection reservoir modules for a geothermal doublet."""

from typing import Literal

import numpy as np

from gemini.core.modules.module import Module
from gemini.core.physics import hydraulics
from gemini.core.types import (
    Control,
    Density,
    Dimensionless,
    Fraction,
    Health,
    Inlet,
    Length,
    MassFlow,
    Outlet,
    Output,
    Parameter,
    Permeability,
    Pressure,
    PressureDifference,
    ProductivityIndex,
    Stream,
    Temperature,
    Viscosity,
)
from gemini.core.types.fluid import Fluid
from gemini.errors import ConfigurationError, InsufficientDataError, PhysicsRangeError

FLUID_OVERRIDES = ("liquid_density", "liquid_viscosity")
"""Reservoir parameters that, when set, replace the matching property of the module fluid."""


class _Reservoir(Module):
    """Common reservoir parameters and measurement helpers."""

    def __init__(self, role):
        super().__init__()

        # Parameters
        self.role = Parameter(Literal["production", "injection"], default=role)
        self.pressure = Parameter(Pressure, calibratable=True)
        self.temperature = Parameter(Temperature)
        self.permeability = Parameter(Permeability)
        self.thickness = Parameter(Length, gt=0)
        self.drainage_radius = Parameter(Length)
        self.top_depth = Parameter(Length)
        self.productivity_index = Parameter(
            ProductivityIndex | None, default=None, calibratable=True
        )
        self.injectivity_index = Parameter(
            ProductivityIndex | None, default=None, calibratable=True
        )
        self.skin = Parameter(Dimensionless, default=0, calibratable=True)
        self.wellbore_radius = Parameter(Length, gt=0)
        self.liquid_density = Parameter(Density | None, default=None)
        self.liquid_viscosity = Parameter(Viscosity | None, default=None)
        self.decline_threshold = Parameter(Fraction, default=0.15, gt=0, le=1)

        # Outputs
        self.bottomhole_pressure = Output(Pressure, soft_sensor=True)
        self.drawdown = Output(PressureDifference)
        self.overpressure = Output(PressureDifference)
        self.flow_dp = Output(PressureDifference | None)
        self.skin_dp = Output(PressureDifference | None)
        self.hydrostatic_dp = Output(PressureDifference)
        self.radial_bottomhole_pressure = Output(Pressure | None)

    @property
    def fluid(self):
        """Return the module fluid with the reservoir's liquid density and viscosity overrides."""
        overrides = {name: getattr(self, name) for name in FLUID_OVERRIDES}
        set_overrides = {name: value for name, value in overrides.items() if value is not None}
        return Fluid.model_validate(self._fluid.model_dump() | set_overrides)

    @fluid.setter
    def fluid(self, value):
        """Set and validate the module fluid without the overrides; ``state_dict`` saves it."""
        Module.fluid.fset(self, value)

    def _calculate_outputs(self, flow, p_bh):
        properties = self.fluid.properties(self.pressure, self.temperature)
        if self.drainage_radius == 0:
            flow_dp = skin_dp = radial = None
        else:
            flow_dp, skin_dp = hydraulics.radial_pressure_drops(
                flow,
                properties.mu_l,
                self.permeability,
                self.thickness,
                self.drainage_radius,
                self.wellbore_radius,
                self.skin,
            )
            radial = self.pressure + flow_dp + skin_dp
        return {
            "bottomhole_pressure": p_bh,
            "drawdown": self.pressure - p_bh if self.role == "production" else 0,
            "overpressure": p_bh - self.pressure if self.role == "injection" else 0,
            "flow_dp": flow_dp,
            "skin_dp": skin_dp,
            "hydrostatic_dp": hydraulics.hydrostatic_dp(properties.rho_l, self.top_depth),
            "radial_bottomhole_pressure": radial,
        }

    @staticmethod
    def estimate_pressure(flows, bottomhole_pressures) -> tuple[float, float]:
        """Fit reservoir pressure [Pa] and R-squared from flow observations."""
        q, p = map(lambda value: np.asarray(value, dtype=float), (flows, bottomhole_pressures))
        if (
            q.shape != p.shape
            or q.ndim != 1
            or len(q) < 2
            or np.any(q == 0)
            or not np.isfinite([q, p]).all()
        ):
            raise InsufficientDataError(
                "Reservoir pressure estimation needs at least two matching finite, nonzero samples"
            )
        x, y = 1 / q, p / q
        if np.ptp(x) == 0 or np.ptp(y) == 0:
            raise InsufficientDataError("Reservoir pressure regression requires variation")
        coefficients = np.polyfit(x, y, 1)
        residual = y - np.poly1d(coefficients)(x)
        r_squared = 1 - np.sum(residual**2) / np.sum((y - np.mean(y)) ** 2)
        return float(coefficients[0]), float(r_squared)

    def injectivity_from_measurements(self, flow, p_bh):
        """Return injectivity [m3/s/Pa] from one measurement."""
        if p_bh == self.pressure:
            raise PhysicsRangeError(
                f"{self.path}: bottomhole pressure = reservoir pressure = {p_bh} Pa; "
                "injectivity needs a pressure differential"
            )
        return flow / (p_bh - self.pressure)

    def productivity_from_measurements(self, flow, p_bh):
        """Return productivity [m3/s/Pa] from one measurement."""
        if p_bh == self.pressure:
            raise PhysicsRangeError(
                f"{self.path}: bottomhole pressure = reservoir pressure = {p_bh} Pa; "
                "productivity needs a pressure differential"
            )
        return flow / (self.pressure - p_bh)

    def health(self, result, measured):
        """Alarm on declining measured PI or II relative to design.

        Returns ``None`` (not assessed) without both measurements, without a nonzero design
        index, or when the measured bottomhole pressure equals the reservoir pressure.
        """
        production = self.role == "production"
        nominal = self.productivity_index if production else self.injectivity_index
        if not {"flow", "bottomhole_pressure"} <= measured.keys() or not nominal:
            return None
        if measured["bottomhole_pressure"] == self.pressure:
            return None
        estimate = (
            self.productivity_from_measurements
            if production
            else self.injectivity_from_measurements
        )
        actual = estimate(measured["flow"], measured["bottomhole_pressure"])
        ratio = actual / nominal
        return Health(
            score=min(1, max(0, ratio)),
            alarm=ratio < 1 - self.decline_threshold,
            message=("Productivity" if production else "Injectivity") + " index comparison",
            metrics={"index": actual, "ratio": ratio},
        )


class ProductionReservoir(_Reservoir):
    """Aquifer supplying a production-well sandface stream."""

    def __init__(self):
        """Declare a production reservoir."""
        super().__init__("production")

        # Controls
        self.production_rate = Control(MassFlow, ge=0)

        # Outlets
        self.sandface = Outlet(Stream)

    def forward(self, inlets):
        """Apply the linear production IPR and emit the sandface stream."""

        # Outlets
        sandface = self.sandface_stream(self.production_rate)

        outlets = dict(sandface=sandface)
        return outlets

    def _compute_outputs(self, inlets, outlets):
        sandface = outlets.sandface
        flow = sandface.volumetric_flow()
        for name, value in self._calculate_outputs(flow, sandface.p).items():
            setattr(self, name, value)

    def sandface_stream(self, production_rate):
        """Return the sandface stream [SI] the linear IPR delivers at a production rate [kg/s].

        ``p_bh = pressure - Q / productivity_index`` with the volume flow Q at reservoir
        conditions. ``forward`` uses it for the commanded rate; the nodal solve of
        ``gemini.core.modules.plants.nodal`` uses it for trial rates without a call.
        """
        if self.productivity_index is None:
            raise ConfigurationError(f"{self.path}: productivity_index is required")
        flow = production_rate / self.fluid.properties(self.pressure, self.temperature).rho_l
        p_bh = self.pressure - flow / self.productivity_index
        return Stream(m_dot=production_rate, T=self.temperature, p=p_bh, fluid=self.fluid)


class InjectionReservoir(_Reservoir):
    """Aquifer receiving the injection-well sandface stream."""

    def __init__(self):
        """Declare an injection reservoir."""
        super().__init__("injection")

        # Inlets
        self.sandface = Inlet(Stream)

    def forward(self, inlets):
        """Receive the sandface stream; the aquifer has no outlet."""

        if self.injectivity_index is None:
            raise ConfigurationError(f"{self.path}: injectivity_index is required")
        outlets = dict()
        return outlets

    def _compute_outputs(self, inlets, outlets):
        """Calculate the bottomhole pressure the sandface flow requires."""
        sandface = inlets.sandface
        flow = abs(sandface.m_dot) / self.fluid.properties(sandface.p, sandface.T).rho_l
        for name, value in self._calculate_outputs(flow, self.required_pressure(sandface)).items():
            setattr(self, name, value)

    def required_pressure(self, sandface):
        """Return the bottomhole pressure [Pa] the linear injectivity needs for a sandface stream.

        ``p_bh = pressure + Q / injectivity_index`` with Q the absolute volume flow of the
        stream. The aquifer accepts any arriving stream; the nodal solve of
        ``gemini.core.modules.plants.nodal`` matches the injection well's bottom pressure to
        this value.
        """
        if self.injectivity_index is None:
            raise ConfigurationError(f"{self.path}: injectivity_index is required")
        flow = abs(sandface.m_dot) / self.fluid.properties(sandface.p, sandface.T).rho_l
        return self.pressure + flow / self.injectivity_index
