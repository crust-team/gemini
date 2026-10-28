"""Pipe geometry and explicit configuration loaders salvaged from GEMINI WIMS."""

from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Sequence

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from . import units


def get_tally_from_well_parameters(properties: dict, well_type: str) -> list:
    """Extract the original tally table from a plain parameter dictionary.

    Parameters
    ----------
    properties : dict
        GEMINI property block; depths [m], legacy tally diameters [inch].
    well_type : str
        Parameter prefix, productionwell or injectionwell [-].

    Returns
    -------
    list
        Original tally rows; param_mapping performs diameter conversions before build_path.

    Notes
    -----
    Reference: GEMINI WIMS common.get_tally_from_well_parameters; this is an input
    boundary helper, with no unit interpretation or file access.
    """
    table = properties.get(f"{well_type}_tally_table", [])
    return list(table[0]) if table and isinstance(table[0], list) else list(table)


def get_esp_depth_m(properties: dict) -> float | None:
    """Extract ESP setting depth from plain configuration data.

    Parameters
    ----------
    properties : dict
        GEMINI property block containing scalar or timestamped esp_depth [m].

    Returns
    -------
    float or None
        First setting depth [m], or None when absent.

    Notes
    -----
    Reference: GEMINI WIMS common.get_esp_depth_m.
    """
    value = properties.get("esp_depth")
    return float(value[0] if isinstance(value, list) else value) if value is not None else None


def get_esp_joint_start_idx(well_tally: Sequence[dict], esp_depth_m: float | None) -> int:
    """Locate the first tally joint starting at or below the pump.

    Parameters
    ----------
    well_tally : sequence of dict
        Ordered tally records with TopMD [m].
    esp_depth_m : float or None
        Pump setting depth [m]; None starts at the first joint.

    Returns
    -------
    int
        Joint index [-], or the tally length when no joint starts below the pump.

    Notes
    -----
    Reference: GEMINI WIMS common.get_esp_joint_start_idx; joint-start selection is
    retained separately from geometric interval intersection.
    """
    if esp_depth_m is None:
        return 0

    for idx, entry in enumerate(well_tally):
        if float(entry["TopMD"]) >= esp_depth_m:
            return idx
    return len(well_tally)


def build_trajectory_geometry(well_traj: list[dict]) -> dict[str, list[float]]:
    """Build the original section arrays from a trajectory table.

    Parameters
    ----------
    well_traj : list of dict
        Ordered MD, TVD, ID and roughness values [m].

    Returns
    -------
    dict of list
        Length, diameter and roughness [m], inclination above horizontal [rad].

    Notes
    -----
    Reference: GEMINI WIMS common.build_trajectory_geometry; inclination is rounded
    to 0.01 degree before conversion to radians, with endpoint diameter selection.
    """
    length = []
    diameter = []
    angle = []
    roughness = []

    for ii in range(1, len(well_traj)):
        md = well_traj[ii]["MD"] - well_traj[ii - 1]["MD"]
        tvd = well_traj[ii]["TVD"] - well_traj[ii - 1]["TVD"]
        length.append(md)
        diameter.append(well_traj[ii]["ID"])
        angle.append(units.deg_to_rad(np.round(90 - units.rad_to_deg(np.arccos(tvd / md)), 2)))
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

    Notes
    -----
    Reference: GEMINI WIMS build_trajectory_geometry, extended with SI tally
    interval intersections. Inclination follows sin(angle) = delta_TVD / delta_MD.
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
        angle = units.deg_to_rad(np.round(90 - units.rad_to_deg(np.arccos(vertical / length)), 2))
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
    """Locate the pipe interval containing the ESP.

    Parameters
    ----------
    path : PipePath
        Pipe sections ordered by increasing measured depth [m].
    esp_depth : float
        Pump measured setting depth [m].

    Returns
    -------
    int
        Section index [-]; a joint boundary selects the deeper section.

    Notes
    -----
    Reference: Measured-depth interval intersection; see PipePath.index_at_measured_depth.
    """
    return path.index_at_measured_depth(esp_depth)


def load_trajectory_csv(path: str | Path) -> list[dict]:
    """Read a semicolon-delimited trajectory at the file boundary.

    Parameters
    ----------
    path : str or pathlib.Path
        Trajectory CSV filename [-].

    Returns
    -------
    list of dict
        MD, TVD, ID and roughness as floats [m], with other columns preserved.

    Notes
    -----
    Reference: GEMINI example well_trajectory.csv schema. This loader is the explicit
    I/O boundary; geometry calculations only accept the returned plain data.
    """
    with Path(path).open(newline="") as handle:
        return [
            {k: float(v) if k in {"MD", "TVD", "ID", "roughness"} else v for k, v in row.items()}
            for row in csv.DictReader(handle, delimiter=";")
        ]


def annulus_id_m(outer_id_m: float, inner_od_m: float) -> float:
    """Calculate the equal-area diameter of an annulus.

    Parameters
    ----------
    outer_id_m, inner_od_m : float
        Outer pipe internal diameter and inner pipe external diameter [m].

    Returns
    -------
    float
        Equal-area circular diameter [m], or zero if the annulus is closed.

    Notes
    -----
    Reference: GEMINI WIMS erosion geometry; sqrt(outer_id**2-inner_od**2).
    """
    return math.sqrt(outer_id_m**2 - inner_od_m**2) if inner_od_m < outer_id_m else 0.0


def flow_cross_section_area_m2(
    flow_area_type: str,
    flow_diameter_m: float,
    outer_id_m: float | None = None,
    inner_od_m: float | None = None,
) -> float:
    """Calculate circular or annular flow area.

    Parameters
    ----------
    flow_area_type : str
        Annulus selector; other values retain the circular-flow calculation [-].
    flow_diameter_m : float
        Circular internal diameter [m].
    outer_id_m, inner_od_m : float, optional
        Outer pipe ID and inner pipe OD for annular flow [m].

    Returns
    -------
    float
        Available flow area [m2].

    Notes
    -----
    Reference: GEMINI WIMS erosion geometry; circular area pi*d**2/4, subtracting
    the inner pipe area for an annulus.
    """
    if flow_area_type == "annulus" and outer_id_m is not None and inner_od_m is not None:
        return math.pi * annulus_id_m(outer_id_m, inner_od_m) ** 2 / 4
    return math.pi * max(0, flow_diameter_m) ** 2 / 4
