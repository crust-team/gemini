"""Serializable plant selection, dated design data and measured-boundary bindings."""

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from gemini.core.types.fluid import BRINE, Fluid


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


class ModuleConfig(ConfigModel):
    """Registered equipment type and ordered parameter history."""

    type: str
    params: list[DatedParams] = Field(min_length=1)
    fluid: Fluid = BRINE

    @field_validator("params")
    @classmethod
    def sort_snapshots(cls, values):
        """Order snapshots and reject ambiguous effective dates."""
        dates = [p.valid_from for p in values]
        if len(set(dates)) != len(dates):
            raise ValueError("Duplicate parameter effective dates")
        return sorted(
            values, key=lambda p: p.valid_from or datetime.min.replace(tzinfo=timezone.utc)
        )

    def at(self, at=None):
        """Select the latest applicable full snapshot, raising before the first snapshot."""
        eligible = [
            p for p in self.params if at is None or p.valid_from is None or p.valid_from <= utc(at)
        ]
        if not eligible:
            raise ValueError(f"{self.type}: no parameters valid at {at}")
        return eligible[-1]


class Binding(ConfigModel):
    """Raw data column and its physical unit at the input boundary."""

    column: str
    unit: str


class ModuleBindings(ConfigModel):
    """Operating controls, inlet conditions and measured outputs for one module."""

    inputs: dict[str, Binding] = Field(default_factory=dict)
    streams: dict[str, dict[str, Binding]] = Field(default_factory=dict)
    measured: dict[str, Binding] = Field(default_factory=dict)


class PlantConfig(ConfigModel):
    """Portable plant design and data bindings, including explicit import diagnostics."""

    name: str
    modules: dict[str, ModuleConfig]
    plant_type: str
    bindings: dict[str, ModuleBindings] = Field(default_factory=dict)
    boundary: dict[str, Any] = Field(default_factory=dict)
    timestep: float = Field(900, gt=0)
    ignored: dict[str, str] = Field(default_factory=dict)
    unmapped: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def references(self):
        """Reject invalid child paths and bindings before plant construction."""
        for name in self.modules:
            if any(
                not part.isidentifier() or part.lower() != part or part.startswith("_")
                for part in name.split(".")
            ):
                raise ValueError(f"Module path must be public snake_case: {name!r}")
        if self.bindings.keys() - self.modules.keys():
            raise ValueError("Bindings reference unknown modules")
        return self
