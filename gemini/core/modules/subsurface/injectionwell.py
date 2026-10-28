"""InjectionWell module.

Traverses a geothermal well using the original GEMINI DPDT equations,
Swamee–Jain (1976) friction, Beggs–Brill two-phase flow and explicit heat loss.
"""

from typing import Literal

from gemini.core.modules.module import Module
from gemini.core.physics import geometry, hydraulics
from gemini.core.types import (
    Dimensionless,
    HeatFlow,
    HeatTransferCoefficient,
    Inlet,
    Outlet,
    Output,
    Parameter,
    Pressure,
    PressureDifference,
    Stream,
    Temperature,
)


class InjectionWell(Module):
    """Passive injectionwell pressure and temperature profile with integrity hooks."""

    def __init__(self):
        """Declare injection-well geometry, inlet and outputs."""
        super().__init__()

        # Parameters
        self.pipe_path = Parameter(geometry.PipePath)
        self.friction_correlation = Parameter(Literal["darcy_weisbach"], default="darcy_weisbach")
        self.friction_correlation_2p = Parameter(Literal["BeggsBrill"], default="BeggsBrill")
        self.correction_factors = Parameter(
            tuple[Dimensionless, PressureDifference], default=(1, 0), calibratable=True
        )
        self.soil_temperature = Parameter(Temperature)
        self.u_value = Parameter(HeatTransferCoefficient, default=10, ge=0, calibratable=True)

        # Inlets
        self.wellhead = Inlet(Stream)

        # Outputs
        self.bottomhole_pressure = Output(Pressure, soft_sensor=True)
        self.bottomhole_temperature = Output(Temperature)
        self.dp_friction = Output(PressureDifference)
        self.dp_gravity = Output(PressureDifference)
        self.section_pressure = Output(list[Pressure])
        self.section_temperature = Output(list[Temperature])

        # Outlets
        self.bottom = Outlet(Stream)
        self.heat_loss = Outlet(HeatFlow)

    def forward(self, wellhead):
        """Traverse the injection path with the legacy negative flow convention."""

        # Outputs
        stream = wellhead
        # NOTE(refactor): legacy injection DPDT uses negative flow; retain that sign convention.
        stream = stream.with_(m_dot=-abs(stream.m_dot))
        result = self.traverse(stream, 0, self.pipe_path.total_length, "down")
        a, b = self.correction_factors
        # NOTE(refactor): negative flow is internal to DPDT; ports preserve incoming mass sign.
        self.bottomhole_pressure = a * result.p_out + b
        self.bottomhole_temperature = result.T_out
        self.dp_friction = result.dp_fric
        self.dp_gravity = result.dp_grav
        self.section_pressure = result.section_p
        self.section_temperature = result.section_T

        # Outlets
        bottom = stream.with_(
            p=self.bottomhole_pressure,
            T=self.bottomhole_temperature,
            m_dot=wellhead.m_dot,
        )
        heat_loss = HeatFlow(
            Q=bottom.m_dot
            * stream.fluid.properties(stream.p, stream.T).cp_l
            * (stream.T - bottom.T),
            T=self.soil_temperature,
        )

        outlets = dict(bottom=bottom, heat_loss=heat_loss)
        return outlets

    def traverse(self, stream, from_md: float, to_md: float, direction: Literal["up", "down"]):
        """Traverse an arbitrary depth interval [m], returning uncorrected SI conditions."""
        p = self
        if (direction == "up" and to_md > from_md) or (direction == "down" and to_md < from_md):
            raise ValueError(f"{self.name}: depth interval conflicts with direction {direction}")
        return hydraulics.pipe_path_profile(
            p.pipe_path.subpath(from_md, to_md),
            stream,
            stream.fluid,
            direction,
            p.u_value,
            p.soil_temperature,
            p.friction_correlation,
            p.friction_correlation_2p,
        )

    def corrosion_profile(
        self, stream, chemistry: dict | None = None, model: str = "NORSOK"
    ) -> list[float]:
        """Return per-section CO2 corrosion [mm/year] using SI chemistry inputs."""
        # NOTE(refactor): corrosion/erosion helpers retain their documented mm/year
        # convention; physics and golden values are unchanged (explicit SI exception).
        if chemistry is None:
            chemistry = stream.fluid.corrosion_inputs(stream.p, stream.T)
            if stream.fluid.co2_mass_fraction == 0:
                return [0.0] * len(self.pipe_path.sections)
        return hydraulics.corrosion_profile(
            self.pipe_path,
            stream.with_(m_dot=-abs(stream.m_dot)),
            stream.fluid,
            "down",
            self.u_value,
            self.soil_temperature,
            chemistry,
            model,
        )

    def erosion_check(self, stream) -> dict:
        """Compare section velocities [m/s] with the API erosional velocity limit."""
        return hydraulics.erosion_check(self.pipe_path, stream, stream.fluid)
