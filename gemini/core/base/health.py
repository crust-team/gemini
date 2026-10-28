"""Equipment monitoring health."""

from pydantic import BaseModel, ConfigDict, Field


class Health(BaseModel):
    """Comparison of predicted equipment performance with measurements."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    score: float = Field(..., ge=0, le=1, description="Condition score, one is nominal [-]")
    alarm: bool = Field(..., description="Whether a monitoring limit is exceeded [-]")
    message: str = Field(..., description="Explanation of the condition [-]")
    metrics: dict[str, float] = Field(
        default_factory=dict, description="Named diagnostic metrics [-]"
    )
