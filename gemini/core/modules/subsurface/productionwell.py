"""ProductionWell module.

Traverses a geothermal well using the original GEMINI DPDT equations,
Swamee–Jain (1976) friction, Beggs–Brill two-phase flow and explicit heat loss.
"""

from typing import Literal

from gemini.core.modules.module import Module
from gemini.core.physics import geometry, hydraulics
from gemini.core.types import (
    Dimensionless,
    HeatTransferCoefficient,
    Inlet,
    Length,
    Outlet,
    Output,
    Parameter,
    Power,
    Pressure,
    PressureDifference,
    Stream,
    Temperature,
)


class ProductionWell(Module):
    """Passive productionwell pressure and temperature profile with integrity hooks."""

    repr_fields = ("segment", "esp_depth", "soil_temperature", "u_value")

    def __init__(self):
        """Declare production-well geometry, inlet and outputs."""
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
        self.segment = Parameter(Literal["full", "below_esp", "above_esp"], default="full")
        self.esp_depth = Parameter(Length | None, default=None)

        # Inlets
        self.bottom = Inlet(Stream)

        # Outputs
        self.wellhead_pressure = Output(Pressure, soft_sensor=True)
        self.wellhead_temperature = Output(Temperature, soft_sensor=True)
        self.dp_friction = Output(PressureDifference)
        self.dp_gravity = Output(PressureDifference)
        self.section_pressure = Output(list[Pressure])
        self.section_temperature = Output(list[Temperature])
        self.heat_loss = Output(Power)

        # Outlets
        self.wellhead = Outlet(Stream)

    def forward(self, inlets):
        """Traverse the passive full path; an internal ESP is handled with the split helpers."""

        # Outlets
        bottom = inlets.bottom
        stream = bottom
        start, end = self.pipe_path.total_length, 0
        if self.segment == "below_esp":
            end = self._esp_depth()
        elif self.segment == "above_esp":
            start = self._esp_depth()
        result = self.traverse(stream, start, end, "up")
        a, b = self.correction_factors

        wellhead = stream.with_(p=a * result.p_out + b, T=result.T_out)

        outlets = dict(wellhead=wellhead)
        return outlets

    def _compute_outputs(self, inlets, outlets):
        bottom = inlets.bottom
        wellhead = outlets.wellhead
        start, end = self.pipe_path.total_length, 0
        if self.segment == "below_esp":
            end = self._esp_depth()
        elif self.segment == "above_esp":
            start = self._esp_depth()
        result = self.traverse(bottom, start, end, "up")
        self.wellhead_pressure = wellhead.p
        self.wellhead_temperature = wellhead.T
        self.dp_friction = result.dp_fric
        self.dp_gravity = result.dp_grav
        self.section_pressure = result.section_p
        self.section_temperature = result.section_T
        self.heat_loss = (
            wellhead.m_dot
            * bottom.fluid.properties(bottom.p, bottom.T).cp_l
            * (bottom.T - wellhead.T)
        )

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
            stream,
            stream.fluid,
            "up",
            self.u_value,
            self.soil_temperature,
            chemistry,
            model,
        )

    def erosion_check(self, stream) -> dict:
        """Compare section velocities [m/s] with the API erosional velocity limit."""
        return hydraulics.erosion_check(self.pipe_path, stream, stream.fluid)

    def _esp_depth(self):
        depth = self.esp_depth
        if depth is None or depth > self.pipe_path.total_length:
            raise ValueError(f"productionwell: ESP depth {depth} is not configured within the path")
        return depth

    def intake_conditions(self, bottom_stream):
        """Traverse from the sandface to ESP intake, returning a stream in SI units."""
        result = self.traverse(bottom_stream, self.pipe_path.total_length, self._esp_depth(), "up")
        a, b = self.correction_factors
        return bottom_stream.with_(p=a * result.p_out + b, T=result.T_out)

    def wellhead_from_discharge(self, discharge_stream):
        """Traverse from ESP discharge to wellhead, returning a stream in SI units."""
        result = self.traverse(discharge_stream, self._esp_depth(), 0, "up")
        a, b = self.correction_factors
        return discharge_stream.with_(p=a * result.p_out + b, T=result.T_out)

    def discharge_from_wellhead(self, wellhead_stream):
        """Infer ESP discharge from measured wellhead conditions using downward traversal."""
        result = self.traverse(wellhead_stream, 0, self._esp_depth(), "down")
        a, b = self.correction_factors
        return wellhead_stream.with_(p=a * result.p_out + b, T=result.T_out)

    def bottomhole_from_wellhead(self, wellhead_stream):
        """Infer passive-path bottomhole conditions; no internal pump boost is inferred."""
        result = self.traverse(wellhead_stream, 0, self.pipe_path.total_length, "down")
        a, b = self.correction_factors
        return wellhead_stream.with_(p=a * result.p_out + b, T=result.T_out)
