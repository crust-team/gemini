"""Production and injection reservoir components for a geothermal doublet.

References: Tarek Ahmed, Reservoir Engineering Handbook (2019), chapter 7;
Akin (2019), geothermal re-injection surveillance and pressure estimation.
"""

from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from gemini.core.base.component import Component, Health
from gemini.core.base.stream import Stream
from gemini.core.physics import hydraulics


class _Reservoir(Component):
    """Common reservoir parameters and measurement helpers; ports remain static in subclasses."""

    category = "subsurface"
    soft_sensors = ("bottomhole_pressure",)
    calibratable = ("productivity_index", "injectivity_index", "pressure", "skin")

    class Params(BaseModel):
        """Reservoir and near-well formation properties in SI units."""

        model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
        role: Literal["production", "injection"] = Field(..., description="Side of the doublet [-]")
        pressure: float = Field(..., ge=0, description="Static reservoir pressure [Pa]")
        temperature: float = Field(..., gt=0, description="Reservoir temperature [K]")
        permeability: float = Field(..., gt=0, description="Absolute permeability [m2]")
        thickness: float = Field(..., gt=0, description="Reservoir thickness [m]")
        drainage_radius: float = Field(
            ..., ge=0, description="Drainage radius; zero means unconfigured [m]"
        )
        top_depth: float = Field(..., ge=0, description="Top reservoir vertical depth [m]")
        productivity_index: float | None = Field(
            None, gt=0, description="Productivity index [m3/s/Pa]"
        )
        injectivity_index: float | None = Field(
            None, gt=0, description="Injectivity index [m3/s/Pa]"
        )
        skin: float = Field(0, description="Dimensionless skin factor [-]")
        wellbore_radius: float = Field(..., gt=0, description="Effective wellbore radius [m]")
        liquid_density: float | None = Field(
            None, gt=0, description="Liquid density override [kg/m3]"
        )
        liquid_viscosity: float | None = Field(
            None, gt=0, description="Liquid viscosity override [Pa s]"
        )
        decline_threshold: float = Field(
            0.15, gt=0, le=1, description="PI or II decline alarm fraction [-]"
        )

        @model_validator(mode="after")
        def required_index(self):
            """Require the well index used by this reservoir's role."""
            key = "productivity_index" if self.role == "production" else "injectivity_index"
            if getattr(self, key) is None:
                raise ValueError(f"{self.role}_reservoir requires {key}")
            return self

    class Outputs(BaseModel):
        """IPR and radial-flow pressures for one well."""

        bottomhole_pressure: float = Field(..., description="Required sandface pressure [Pa]")
        drawdown: float = Field(..., description="Production pressure drawdown [Pa]")
        overpressure: float = Field(..., description="Injection pressure excess [Pa]")
        flow_dp: float | None = Field(..., description="Radial Darcy pressure drop [Pa]")
        skin_dp: float | None = Field(..., description="Skin pressure drop [Pa]")
        hydrostatic_dp: float = Field(..., description="Hydrostatic pressure contribution [Pa]")
        radial_bottomhole_pressure: float | None = Field(
            ..., description="Legacy radial reservoir pressure [Pa]"
        )

    def _outputs(self, flow, p_bh):
        p = self.params
        f = self.fluid.properties(p.pressure, p.temperature)
        if p.drainage_radius == 0:
            # NOTE(refactor): injection example radius=0 made log(radius/rw)=-inf; expose
            # unavailable radial diagnostics as None.
            flow_dp = skin_dp = radial = None
        else:
            flow_dp, skin_dp = hydraulics.radial_pressure_drops(
                flow,
                f.mu_l,
                p.permeability,
                p.thickness,
                p.drainage_radius,
                p.wellbore_radius,
                p.skin,
            )
            # Preserve the original radial model's plus sign for both reservoir roles.
            radial = p.pressure + flow_dp + skin_dp
        return self.Outputs(
            bottomhole_pressure=p_bh,
            drawdown=p.pressure - p_bh if p.role == "production" else 0,
            overpressure=p_bh - p.pressure if p.role == "injection" else 0,
            flow_dp=flow_dp,
            skin_dp=skin_dp,
            hydrostatic_dp=hydraulics.hydrostatic_dp(f.rho_l, p.top_depth),
            radial_bottomhole_pressure=radial,
        )

    @staticmethod
    def estimate_pressure(flows, bottomhole_pressures) -> tuple[float, float]:
        """Fit pressure [Pa] and R-squared [-] from flows [m3/s] and BHP [Pa] (Akin 2019)."""
        q, p = map(lambda v: np.asarray(v, dtype=float), (flows, bottomhole_pressures))
        if (
            q.shape != p.shape
            or q.ndim != 1
            or len(q) < 2
            or np.any(q == 0)
            or not np.isfinite([q, p]).all()
        ):
            raise ValueError(
                "Reservoir pressure estimation needs matching finite, nonzero flow samples"
            )
        x, y = 1 / q, p / q
        if np.ptp(x) == 0 or np.ptp(y) == 0:
            raise ValueError("Reservoir pressure regression requires variation in 1/Q and p/Q")
        coefficients = np.polyfit(x, y, 1)
        residual = y - np.poly1d(coefficients)(x)
        r_squared = 1 - np.sum(residual**2) / np.sum((y - np.mean(y)) ** 2)
        return float(coefficients[0]), float(r_squared)

    def injectivity_from_measurements(self, flow: float, p_bh: float) -> float:
        """Return II [m3/s/Pa] from volume flow [m3/s] and sandface pressure [Pa]."""
        if p_bh == self.params.pressure:
            raise ValueError("Injection reservoir: zero pressure differential")
        return flow / (p_bh - self.params.pressure)

    def productivity_from_measurements(self, flow: float, p_bh: float) -> float:
        """Return PI [m3/s/Pa] from volume flow [m3/s] and sandface pressure [Pa]."""
        if p_bh == self.params.pressure:
            raise ValueError("Production reservoir: zero pressure differential")
        return flow / (self.params.pressure - p_bh)

    def health(self, predicted, measured):
        """Alarm on declining measured PI or II relative to the design index."""
        if not {"flow", "bottomhole_pressure"} <= measured.keys():
            return None
        production = self.params.role == "production"
        helper = (
            self.productivity_from_measurements
            if production
            else self.injectivity_from_measurements
        )
        actual = helper(measured["flow"], measured["bottomhole_pressure"])
        nominal = self.params.productivity_index if production else self.params.injectivity_index
        ratio = actual / nominal
        return Health(
            score=min(1, max(0, ratio)),
            alarm=ratio < 1 - self.params.decline_threshold,
            message=("Productivity" if production else "Injectivity") + " index comparison",
            metrics={"index": actual, "ratio": ratio},
        )


class ProductionReservoir(_Reservoir):
    """Aquifer supplying a production-well sandface stream."""

    name = "production_reservoir"
    description = "Production aquifer with productivity and radial-flow diagnostics."
    outlets = ("sandface",)

    class Params(_Reservoir.Params):
        """Production-side reservoir design data."""

        role: Literal["production"] = Field("production", description="Side of the doublet [-]")

    class Inputs(BaseModel):
        """Mass withdrawal imposed by the caller."""

        model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
        m_dot: float = Field(..., ge=0, description="Produced mass flow [kg/s]")

    def compute(self, inputs, streams_in):
        """Apply the linear production IPR and emit the sandface stream."""
        p = self.params
        flow = inputs.m_dot / self.fluid.properties(p.pressure, p.temperature).rho_l
        p_bh = p.pressure - flow / p.productivity_index
        stream = Stream(m_dot=inputs.m_dot, T=p.temperature, p=p_bh, fluid=self.fluid_name)
        return self._outputs(flow, p_bh), {"sandface": stream}


class InjectionReservoir(_Reservoir):
    """Aquifer receiving the injection-well sandface stream."""

    name = "injection_reservoir"
    description = "Injection aquifer with injectivity and radial-flow diagnostics."
    inlets = ("sandface",)

    class Params(_Reservoir.Params):
        """Injection-side reservoir design data."""

        role: Literal["injection"] = Field("injection", description="Side of the doublet [-]")

    class Inputs(BaseModel):
        """The inlet stream supplies all operating conditions."""

        model_config = ConfigDict(extra="forbid")

    def compute(self, inputs, streams_in):
        """Calculate required injection bottomhole pressure from the sandface flow."""
        stream = streams_in["sandface"]
        flow = abs(stream.m_dot) / self.fluid.properties(stream.p, stream.T).rho_l
        p_bh = self.params.pressure + flow / self.params.injectivity_index
        return self._outputs(flow, p_bh), {}
