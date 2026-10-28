"""Serializable plant selection, dated design data and measured-boundary bindings."""

from datetime import datetime, timezone
from typing import Any

from pydantic import Field, field_validator, model_validator

from gemini.core.types.bindings import Binding, ConfigModel, DatedParams, ModuleBindings, utc

__all__ = ["Binding", "DatedParams", "ModuleBindings", "ModuleConfig", "PlantConfig"]

from gemini.core.types.fluid import BRINE, Fluid


class ModuleConfig(ConfigModel):
    """Registered equipment type and ordered parameter history."""

    type: str
    params: list[DatedParams] = Field(min_length=1)
    fluid: Fluid = BRINE
    overrides: dict[str, Any] = Field(default_factory=dict)
    active_from: datetime | None = None

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


class PlantConfig(ConfigModel):
    """Portable plant design and data bindings, including explicit import diagnostics."""

    name: str
    modules: dict[str, ModuleConfig]
    composites: dict[str, ModuleConfig] = Field(default_factory=dict)
    plant_type: str
    bindings: dict[str, ModuleBindings] = Field(default_factory=dict)
    boundary: dict[str, Any] = Field(default_factory=dict)
    timestep: float = Field(900, gt=0)
    ignored: dict[str, str] = Field(default_factory=dict)
    state: dict[str, Any] = Field(default_factory=dict)
    unmapped: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def references(self):
        """Reject invalid child paths and bindings before plant construction."""
        for name in self.modules:
            if name and any(
                not part.isidentifier() or part.lower() != part or part.startswith("_")
                for part in name.split(".")
            ):
                raise ValueError(f"Module path must be public snake_case: {name!r}")
        if self.bindings.keys() - self.modules.keys() - {""}:
            raise ValueError("Bindings reference unknown modules")
        return self
