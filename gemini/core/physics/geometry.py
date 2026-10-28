"""Shared helpers for WIMS application workflows."""

from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Iterable

import numpy as np
from pydantic import BaseModel, ConfigDict, Field


def get_tally_from_well_parameters(properties: dict, well_type: str) -> list:
    """Read the first tally [m, inch] from a plain GEMINI property block."""
    table = properties.get(f"{well_type}_tally_table", [])
    return list(table[0]) if table and isinstance(table[0], list) else list(table)


def get_esp_depth_m(properties: dict) -> float | None:
    """Read ESP setting depth [m] from a plain GEMINI property block."""
    value = properties.get("esp_depth")
    return float(value[0] if isinstance(value, list) else value) if value is not None else None


def get_esp_joint_start_idx(well_tally: Iterable, esp_depth_m):
    """Return the first tally index at or below the ESP setting depth."""
    if esp_depth_m is None:
        return 0

    for idx, entry in enumerate(well_tally):
        if float(entry["TopMD"]) >= esp_depth_m:
            return idx
    return len(well_tally)


def build_trajectory_geometry(well_traj):
    """Build section arrays from a trajectory table."""
    length = []
    diameter = []
    angle = []
    roughness = []

    for ii in range(1, len(well_traj)):
        md = well_traj[ii]["MD"] - well_traj[ii - 1]["MD"]
        tvd = well_traj[ii]["TVD"] - well_traj[ii - 1]["TVD"]
        length.append(md)
        diameter.append(well_traj[ii]["ID"])
        angle.append((np.round(90 - np.arccos(tvd / md) * 180 / np.pi, 2)) * np.pi / 180)
        roughness.append(well_traj[ii]["roughness"])

    return {
        "length": length,
        "diameter": diameter,
        "angle": angle,
        "roughness": roughness,
    }


class PipeSection(BaseModel):
    """A constant-diameter pipe interval, ordered from surface to bottom."""

    model_config = ConfigDict(frozen=True)
    length: float = Field(..., ge=0, description="Measured interval length [m]")
    inclination: float = Field(
        ..., ge=-math.pi / 2, le=math.pi / 2, description="Inclination [rad]"
    )
    inner_diameter: float = Field(..., gt=0, description="Internal diameter [m]")
    roughness: float = Field(..., ge=0, description="Absolute roughness [m]")


class PipePath(BaseModel):
    """Ordered pipe sections in increasing measured depth."""

    sections: list[PipeSection] = Field(default_factory=list, description="Pipe intervals [-]")

    @property
    def total_length(self) -> float:
        """Return measured path length [m]."""
        return sum(s.length for s in self.sections)

    @property
    def true_vertical_depth(self) -> float:
        """Return vertical projection of the rounded legacy inclinations [m]."""
        return sum(s.length * math.sin(s.inclination) for s in self.sections)

    def index_at_measured_depth(self, md: float) -> int:
        """Return the interval containing depth [m], choosing the deeper interval at a joint."""
        if not 0 <= md <= self.total_length or not self.sections:
            raise ValueError(f"Measured depth {md} outside path [0, {self.total_length}]")
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
            raise ValueError(
                f"Depth interval [{low}, {high}] outside path [0, {self.total_length}]"
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
    """
    if not trajectory_table or len(trajectory_table) < 2:
        raise ValueError("A pipe path requires at least two trajectory points")
    rows = trajectory_table
    sections = []
    for first, last in zip(rows, rows[1:]):
        length = last["MD"] - first["MD"]
        vertical = last["TVD"] - first["TVD"]
        if length <= 0 or abs(vertical) > length:
            raise ValueError("Trajectory MD must increase and |delta TVD| must not exceed delta MD")
        angle = np.round(90 - np.arccos(vertical / length) * 180 / np.pi, 2) * np.pi / 180
        cuts = {first["MD"], last["MD"]}
        for row in tally_table or []:
            cuts.update(d for d in (row["TopMD"], row["BottomMD"]) if first["MD"] < d < last["MD"])
        cuts = sorted(cuts)
        for low, high in zip(cuts, cuts[1:]):
            tally = next(
                (r for r in tally_table or [] if r["TopMD"] <= (low + high) / 2 < r["BottomMD"]), {}
            )
            # NOTE(refactor): example roughness 2e-5 is metres, despite DPDT's old mm comment.
            sections.append(
                PipeSection(
                    length=high - low,
                    inclination=angle,
                    inner_diameter=tally.get("ID", last["ID"]),
                    roughness=tally.get("roughness", last["roughness"]),
                )
            )
    return PipePath(sections=sections)


def esp_section_index(path: PipePath, esp_depth: float) -> int:
    """Locate an ESP by measured setting depth [m]."""
    return path.index_at_measured_depth(esp_depth)


def load_trajectory_csv(path: str | Path) -> list[dict]:
    """Read semicolon-delimited trajectory MD/TVD/ID/roughness [m] at the file boundary."""
    with Path(path).open(newline="") as handle:
        return [
            {k: float(v) if k in {"MD", "TVD", "ID", "roughness"} else v for k, v in row.items()}
            for row in csv.DictReader(handle, delimiter=";")
        ]


def annulus_id_m(outer_id_m: float, inner_od_m: float) -> float:
    """Return equal-area annulus diameter [m], as in the WIMS erosion geometry."""
    return math.sqrt(outer_id_m**2 - inner_od_m**2) if inner_od_m < outer_id_m else 0.0


def flow_cross_section_area_m2(
    flow_area_type: str,
    flow_diameter_m: float,
    outer_id_m: float | None = None,
    inner_od_m: float | None = None,
) -> float:
    """Return circular or annular flow area [m2] from diameters [m]."""
    if flow_area_type == "annulus" and outer_id_m is not None and inner_od_m is not None:
        return math.pi * annulus_id_m(outer_id_m, inner_od_m) ** 2 / 4
    return math.pi * max(0, flow_diameter_m) ** 2 / 4
