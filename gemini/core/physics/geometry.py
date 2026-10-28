"""Shared helpers for WIMS application workflows."""

from __future__ import annotations

from typing import Iterable

import numpy as np


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
