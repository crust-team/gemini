"""Portable sensor and dated-parameter metadata shared by modules and data."""

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


def utc(value):
    """Normalise naive project timestamps and aware timestamps to UTC."""
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )


class ConfigModel(BaseModel):
    """Reject misspelled configuration fields."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class DatedParams(ConfigModel):
    """Complete parameter snapshot effective from an optional UTC instant."""

    valid_from: datetime | None = None
    params: dict[str, Any]

    @field_validator("valid_from")
    @classmethod
    def normalise_time(cls, value):
        """Interpret naive project dates as UTC."""
        return utc(value) if value is not None else None


class Binding(ConfigModel):
    """Raw data column and its physical unit at the input boundary."""

    column: str
    unit: str


class ModuleBindings(ConfigModel):
    """Operating controls, inlet conditions and measured outputs for one module."""

    inputs: dict[str, Binding] = Field(default_factory=dict)
    streams: dict[str, dict[str, Binding]] = Field(default_factory=dict)
    measured: dict[str, Binding] = Field(default_factory=dict)
    state: dict[str, Binding] = Field(default_factory=dict)


class ColumnInfo(ConfigModel):
    """Raw column unit and optional physical quantity."""

    unit: str
    quantity: str | None = None
