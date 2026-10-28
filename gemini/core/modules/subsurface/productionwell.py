"""ProductionWell component.

Traverses a geothermal well using the original GEMINI DPDT equations,
Swamee–Jain (1976) friction, Beggs–Brill two-phase flow and explicit heat loss.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from gemini.core.modules.module import Module, ModuleResult
from gemini.core.physics import geometry, hydraulics


class ProductionWell(Module):
    """Passive productionwell pressure and temperature profile with integrity hooks."""

    name = "productionwell"
    category = "subsurface"
    description = "ProductionWell pressure, temperature, corrosion and erosion diagnostics."
    inlets = ("bottom",)
    outlets = ("wellhead",)
    soft_sensors = ("wellhead_pressure", "wellhead_temperature")
    calibratable = ("correction_factors", "u_value")

    class Params(BaseModel):
        """Pipe path and heat-loss design parameters."""

        model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
        path: geometry.PipePath = Field(..., description="Ordered pipe sections [-]")
        friction_correlation: Literal["darcy_weisbach"] = Field(
            "darcy_weisbach", description="Single-phase correlation [-]"
        )
        friction_correlation_2p: Literal["BeggsBrill"] = Field(
            "BeggsBrill", description="Two-phase correlation [-]"
        )
        correction_factors: tuple[float, float] = Field(
            (1, 0), description="Pressure correction slope [-], offset [Pa]"
        )
        soil_temperature: float = Field(..., gt=0, description="Ambient soil temperature [K]")
        u_value: float = Field(
            10, ge=0, description="Overall pipe heat transfer coefficient [W/m2/K]"
        )
        esp_depth: float | None = Field(None, ge=0, description="Optional ESP measured depth [m]")

    class Inputs(BaseModel):
        """All operating conditions arrive through the inlet stream."""

        model_config = ConfigDict(extra="forbid")

    class Outputs(BaseModel):
        """Outlet conditions and traversed section profiles."""

        wellhead_pressure: float = Field(..., description="Outlet pressure [Pa]")
        wellhead_temperature: float = Field(..., description="Outlet temperature [K]")
        dp_friction: float = Field(..., description="Signed friction pressure drop [Pa]")
        dp_gravity: float = Field(..., description="Gravity pressure drop [Pa]")
        section_pressure: list[float] = Field(..., description="Traversed section pressures [Pa]")
        section_temperature: list[float] = Field(
            ..., description="Traversed section temperatures [K]"
        )

    def forward(self, inputs, streams_in):
        """Traverse the passive full path; an internal ESP is handled with the split helpers."""
        stream = streams_in["bottom"]
        result = self.traverse(stream, self.params.path.total_length, 0, "up")
        a, b = self.params.correction_factors
        output = stream.with_(p=a * result.p_out + b, T=result.T_out)
        return ModuleResult(
            self.Outputs(
                wellhead_pressure=output.p,
                wellhead_temperature=output.T,
                dp_friction=result.dp_fric,
                dp_gravity=result.dp_grav,
                section_pressure=result.section_p,
                section_temperature=result.section_T,
            ),
            {"wellhead": output},
        )

    def traverse(self, stream, from_md: float, to_md: float, direction: Literal["up", "down"]):
        """Traverse an arbitrary depth interval [m], returning uncorrected SI conditions."""
        p = self.params
        if (direction == "up" and to_md > from_md) or (direction == "down" and to_md < from_md):
            raise ValueError(f"{self.name}: depth interval conflicts with direction {direction}")
        return hydraulics.pipe_path_profile(
            p.path.subpath(from_md, to_md),
            stream,
            self.fluid,
            direction,
            p.u_value,
            p.soil_temperature,
            p.friction_correlation,
            p.friction_correlation_2p,
        )

    def corrosion_profile(self, stream, chemistry: dict, model: str = "NORSOK") -> list[float]:
        """Return per-section CO2 corrosion [mm/year] using SI chemistry inputs."""
        return hydraulics.corrosion_profile(
            self.params.path,
            stream,
            self.fluid,
            "up",
            self.params.u_value,
            self.params.soil_temperature,
            chemistry,
            model,
        )

    def erosion_check(self, stream) -> dict:
        """Compare section velocities [m/s] with the API erosional velocity limit."""
        return hydraulics.erosion_check(self.params.path, stream, self.fluid)

    def _esp_depth(self):
        depth = self.params.esp_depth
        if depth is None or depth > self.params.path.total_length:
            raise ValueError(f"productionwell: ESP depth {depth} is not configured within the path")
        return depth

    def intake_conditions(self, bottom_stream):
        """Traverse from the sandface to ESP intake, returning a stream in SI units."""
        result = self.traverse(
            bottom_stream, self.params.path.total_length, self._esp_depth(), "up"
        )
        a, b = self.params.correction_factors
        return bottom_stream.with_(p=a * result.p_out + b, T=result.T_out)

    def wellhead_from_discharge(self, discharge_stream):
        """Traverse from ESP discharge to wellhead, returning a stream in SI units."""
        result = self.traverse(discharge_stream, self._esp_depth(), 0, "up")
        a, b = self.params.correction_factors
        return discharge_stream.with_(p=a * result.p_out + b, T=result.T_out)

    def discharge_from_wellhead(self, wellhead_stream):
        """Infer ESP discharge from measured wellhead conditions using downward traversal."""
        result = self.traverse(wellhead_stream, 0, self._esp_depth(), "down")
        a, b = self.params.correction_factors
        return wellhead_stream.with_(p=a * result.p_out + b, T=result.T_out)

    def bottomhole_from_wellhead(self, wellhead_stream):
        """Infer passive-path bottomhole conditions; no internal pump boost is inferred."""
        result = self.traverse(wellhead_stream, 0, self.params.path.total_length, "down")
        a, b = self.params.correction_factors
        return wellhead_stream.with_(p=a * result.p_out + b, T=result.T_out)
