"""Portable sensor and dated-parameter metadata shared by modules and data."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from gemini._utils.time import to_utc


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
        return to_utc(value) if value is not None else None


class Binding(ConfigModel):
    """Raw data column and its physical unit at the input boundary."""

    column: str
    unit: str


class ModuleBindings(ConfigModel):
    """Operating controls, inlet conditions and measured outputs for one module."""

    controls: dict[str, Binding] = Field(default_factory=dict)
    boundaries: dict[str, Binding] = Field(default_factory=dict)
    inlets: dict[str, dict[str, Binding]] = Field(default_factory=dict)
    measured: dict[str, Binding] = Field(default_factory=dict)
    state: dict[str, Binding] = Field(default_factory=dict)


class ColumnInfo(ConfigModel):
    """Raw column unit and optional physical quantity."""

    unit: str
    quantity: str | None = None
