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
from gemini.core.types.results import Health


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
        self.flow_dp = Output(PressureDifference | None, optional=True)
        self.skin_dp = Output(PressureDifference | None, optional=True)
        self.hydrostatic_dp = Output(PressureDifference)
        self.radial_bottomhole_pressure = Output(Pressure | None, optional=True)

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
            raise ValueError("Reservoir pressure estimation needs matching finite samples")
        x, y = 1 / q, p / q
        if np.ptp(x) == 0 or np.ptp(y) == 0:
            raise ValueError("Reservoir pressure regression requires variation")
        coefficients = np.polyfit(x, y, 1)
        residual = y - np.poly1d(coefficients)(x)
        r_squared = 1 - np.sum(residual**2) / np.sum((y - np.mean(y)) ** 2)
        return float(coefficients[0]), float(r_squared)

    def injectivity_from_measurements(self, flow, p_bh):
        """Return injectivity [m3/s/Pa] from one measurement."""
        if p_bh == self.pressure:
            raise ValueError("Injection reservoir: zero pressure differential")
        return flow / (p_bh - self.pressure)

    def productivity_from_measurements(self, flow, p_bh):
        """Return productivity [m3/s/Pa] from one measurement."""
        if p_bh == self.pressure:
            raise ValueError("Production reservoir: zero pressure differential")
        return flow / (self.pressure - p_bh)

    def health(self, predicted, measured):
        """Alarm on declining measured PI or II relative to design."""
        if not {"flow", "bottomhole_pressure"} <= measured.keys():
            return None
        production = self.role == "production"
        actual = (
            self.productivity_from_measurements
            if production
            else self.injectivity_from_measurements
        )(measured["flow"], measured["bottomhole_pressure"])
        nominal = self.productivity_index if production else self.injectivity_index
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
        self.m_dot = Control(MassFlow, ge=0)

        # Outlets
        self.sandface = Outlet(Stream)

    def forward(self, inlets):
        """Apply the linear production IPR and emit the sandface stream."""

        # Outlets
        if self.productivity_index is None:
            raise ValueError(f"{self.path}: productivity_index is required")
        flow = self.m_dot / self.fluid.properties(self.pressure, self.temperature).rho_l
        p_bh = self.pressure - flow / self.productivity_index

        sandface = Stream(m_dot=self.m_dot, T=self.temperature, p=p_bh, fluid=self.fluid)

        outlets = dict(sandface=sandface)
        return outlets

    def _compute_outputs(self, inlets, outlets):
        sandface = outlets.sandface
        flow = sandface.volumetric_flow()
        for name, value in self._calculate_outputs(flow, sandface.p).items():
            setattr(self, name, value)


class InjectionReservoir(_Reservoir):
    """Aquifer receiving the injection-well sandface stream."""

    def __init__(self):
        """Declare an injection reservoir."""
        super().__init__("injection")

        # Inlets
        self.sandface = Inlet(Stream)

    def forward(self, inlets):
        """Calculate required bottomhole pressure from the sandface flow."""

        outlets = dict()
        return outlets

    def _compute_outputs(self, inlets, outlets):
        sandface = inlets.sandface
        if self.injectivity_index is None:
            raise ValueError(f"{self.path}: injectivity_index is required")
        flow = abs(sandface.m_dot) / self.fluid.properties(sandface.p, sandface.T).rho_l
        p_bh = self.pressure + flow / self.injectivity_index
        for name, value in self._calculate_outputs(flow, p_bh).items():
            setattr(self, name, value)
