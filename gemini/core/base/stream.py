"""Immutable fluid streams exchanged by equipment ports."""

from pydantic import BaseModel, ConfigDict, Field

from gemini.core.physics import fluid


class Stream(BaseModel):
    """Fluid stream passed between component ports (SI units)."""

    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)
    m_dot: float = Field(..., description="Mass flow; negative means reverse [kg/s]")
    T: float = Field(..., gt=0, description="Temperature [K]")
    p: float = Field(..., ge=0, description="Absolute pressure [Pa]")
    fluid: str = Field("brine", description="Registered fluid model name [-]")

    def volumetric_flow(self) -> float:
        """Return signed mixture volume flow [m3/s] using the registered fluid model."""
        return self.m_dot / fluid.get_fluid(self.fluid).properties(self.p, self.T).density

    def with_(self, **changes) -> "Stream":
        """Return a validated copy with updated SI stream fields."""
        # model_copy alone bypasses validation, including physical pressure/temperature limits.
        return type(self).model_validate(self.model_copy(update=changes).model_dump())
