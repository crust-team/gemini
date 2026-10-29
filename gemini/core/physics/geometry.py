"""Pure in-memory pipe geometry calculations."""

from __future__ import annotations

import math

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from gemini.errors import PhysicsRangeError

from . import units


def circle_area(diameter: float) -> float:
    """Return the area [m2] of a circle with ``diameter`` [m], ``pi * d**2 / 4``.

    NORSOK's shear stress keeps its own ``pi * (d / 2) ** 2``, which differs in the last bit.
    """
    return math.pi * diameter**2 / 4


class PipeSection(BaseModel):
    """A constant-diameter pipe interval, ordered from surface to bottom."""

    model_config = ConfigDict(frozen=True)
    length: float = Field(
        ...,
        ge=0,
        description="Measured interval length [m]",
        json_schema_extra={"quantity": "length", "unit": "m"},
    )
    inclination: float = Field(
        ...,
        ge=-math.pi / 2,
        le=math.pi / 2,
        description="Inclination [rad]",
        json_schema_extra={"quantity": "angle", "unit": "rad"},
    )
    inner_diameter: float = Field(
        ...,
        gt=0,
        description="Internal diameter [m]",
        json_schema_extra={"quantity": "length", "unit": "m"},
    )
    roughness: float = Field(
        ...,
        ge=0,
        description="Absolute roughness [m]",
        json_schema_extra={"quantity": "length", "unit": "m"},
    )


class PipePath(BaseModel):
    """Ordered pipe sections in increasing measured depth."""

    sections: list[PipeSection] = Field(default_factory=list, description="Pipe intervals [-]")

    @property
    def total_length(self) -> float:
        """Return measured path length [m]."""
        return sum(s.length for s in self.sections)

    def index_at_measured_depth(self, md: float) -> int:
        """Return the interval containing depth [m], choosing the deeper interval at a joint."""
        if not 0 <= md <= self.total_length or not self.sections:
            raise PhysicsRangeError(
                f"PipePath: measured depth = {md} m; expected a depth in [0, {self.total_length}]"
            )
        depth = 0.0
        for i, section in enumerate(self.sections):
            depth += section.length
            if md < depth:
                return i
        return len(self.sections) - 1

    def subpath(self, start_md: float, end_md: float) -> "PipePath":
        """Slice at arbitrary depths [m], retaining the intersected section geometry."""
        low, high = sorted((start_md, end_md))
        if low < 0 or high > self.total_length:
            raise PhysicsRangeError(
                f"PipePath: depth interval = [{low}, {high}] m; "
                f"expected an interval inside [0, {self.total_length}]"
            )
        depth = 0.0
        selected = []
        for section in self.sections:
            end = depth + section.length
            length = min(high, end) - max(low, depth)
            if length > 0:
                selected.append(section.model_copy(update={"length": length}))
            depth = end
        return PipePath(sections=selected)


def build_path(trajectory_table: list[dict], tally_table: list[dict] | None = None) -> PipePath:
    """Build a path from SI trajectory and optional SI tally intervals.

    Parameters
    ----------
    trajectory_table : list of dict
        MD, TVD, ID and roughness [m]. Endpoint geometry applies to the preceding interval.
    tally_table : list of dict, optional
        TopMD, BottomMD, ID and roughness [m]. Tally diameters override trajectory geometry.

    Returns
    -------
    PipePath
        Sections retaining WIMS' inclination rounding to 0.01 degree.

    Notes
    -----
    Reference: GEMINI WIMS build_trajectory_geometry, extended with SI tally
    interval intersections. Inclination follows sin(angle) = delta_TVD / delta_MD and is
    rounded to 0.01 degree, as in WIMS, so paths match the original section angles.

    NOTE(refactor): example roughness 2e-5 is metres, despite DPDT's old mm comment.
    """
    if not trajectory_table or len(trajectory_table) < 2:
        raise PhysicsRangeError(
            f"build_path: trajectory points = {len(trajectory_table or [])}; expected at least 2"
        )
    sections = []
    for index, (first, last) in enumerate(zip(trajectory_table, trajectory_table[1:]), 1):
        length = last["MD"] - first["MD"]
        vertical = last["TVD"] - first["TVD"]
        if length <= 0 or abs(vertical) > length:
            raise PhysicsRangeError(
                f"build_path: trajectory row {index}: delta MD = {length} m, delta TVD = "
                f"{vertical} m; expected increasing MD and |delta TVD| <= delta MD"
            )
        angle = units.deg_to_rad(np.round(90 - units.rad_to_deg(np.arccos(vertical / length)), 2))
        sections.extend(_interval_sections(first, last, angle, tally_table or []))
    return PipePath(sections=sections)


def _interval_sections(first, last, angle, tally_table):
    """Split one trajectory interval at the tally joints inside it.

    Each piece takes the tally geometry covering its midpoint, otherwise the geometry of the
    interval's end point.
    """
    cuts = {first["MD"], last["MD"]}
    for row in tally_table:
        cuts.update(d for d in (row["TopMD"], row["BottomMD"]) if first["MD"] < d < last["MD"])
    cuts = sorted(cuts)
    sections = []
    for low, high in zip(cuts, cuts[1:]):
        tally = next((r for r in tally_table if r["TopMD"] <= (low + high) / 2 < r["BottomMD"]), {})
        sections.append(
            PipeSection(
                length=high - low,
                inclination=angle,
                inner_diameter=tally.get("ID", last["ID"]),
                roughness=tally.get("roughness", last["roughness"]),
            )
        )
    return sections
