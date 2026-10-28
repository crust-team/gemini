"""Immutable fluid streams exchanged by equipment ports."""

from pydantic import BaseModel, ConfigDict, Field

from gemini.core.types.fluid import BRINE, Fluid
from gemini.core.types.quantities import MassFlow, Pressure, Temperature


class Stream(BaseModel):
    """Fluid stream passed between component ports (SI units)."""

    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)
    m_dot: MassFlow = Field(..., description="Mass flow; negative means reverse [kg/s]")
    T: Temperature = Field(..., gt=0, description="Temperature [K]")
    p: Pressure = Field(..., ge=0, description="Absolute pressure [Pa]")
    fluid: Fluid = Field(BRINE, description="Immutable composition and property model [-]")

    def volumetric_flow(self) -> float:
        """Return signed mixture volume flow [m3/s] using the stream dtype."""
        return self.m_dot / self.fluid.properties(self.p, self.T).density

    def with_(self, **changes) -> "Stream":
        """Return a validated copy with updated SI stream fields."""
        # model_copy alone bypasses validation, including physical pressure/temperature limits.
        return type(self).model_validate(self.model_dump() | changes)
