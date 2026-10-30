"""Pipe sections, measured-depth paths and trajectory/tally construction."""

import math
from pathlib import Path

import pandas as pd
import pytest

from gemini.errors import PhysicsRangeError
from gemini.physics import geometry
from tests.fixtures.equivalence import assert_function_matches

TRAJECTORY = [
    {"MD": 0, "TVD": 0, "ID": 0.2, "roughness": 2e-5},
    {"MD": 100, "TVD": 100, "ID": 0.2, "roughness": 2e-5},
    {"MD": 300, "TVD": 200, "ID": 0.15, "roughness": 3e-5},
]


def test_circle_area():
    """Circle area is pi d^2 / 4."""
    assert geometry.circle_area(2) == math.pi


def test_circle_area_matches_on_arrays():
    """The area runs on arrays as on floats."""
    assert_function_matches(geometry.circle_area, [(2.0,), (0.1778,), (0.0,)])


def test_build_path_angles_and_end_point_geometry():
    """Inclination follows sin(angle) = dTVD/dMD; an interval takes its end-point geometry."""
    path = geometry.build_path(TRAJECTORY)
    assert [s.length for s in path.sections] == [100, 200]
    assert path.sections[0].inclination == pytest.approx(math.pi / 2)
    assert path.sections[1].inclination == pytest.approx(math.radians(30))
    assert path.sections[1].inner_diameter == 0.15
    assert path.total_length == 300


def test_build_path_splits_intervals_at_tally_joints():
    """Tally rows override the geometry they cover and cut intervals at their joints."""
    tally = [{"TopMD": 50, "BottomMD": 150, "ID": 0.1, "roughness": 1e-5}]
    path = geometry.build_path(TRAJECTORY, tally)
    assert [s.length for s in path.sections] == [50, 50, 50, 150]
    assert [s.inner_diameter for s in path.sections] == [0.2, 0.1, 0.1, 0.15]
    assert path.sections[2].inclination == path.sections[3].inclination


def test_build_path_rejects_invalid_trajectories():
    """A path needs two points, increasing MD and |dTVD| <= dMD."""
    with pytest.raises(PhysicsRangeError, match="at least 2"):
        geometry.build_path(TRAJECTORY[:1])
    with pytest.raises(PhysicsRangeError, match="row 1"):
        geometry.build_path([TRAJECTORY[0], {"MD": 10, "TVD": 20, "ID": 0.2, "roughness": 0}])


def test_index_at_measured_depth_and_subpath():
    """Joints select the deeper section; slices conserve length and keep geometry."""
    path = geometry.build_path(TRAJECTORY)
    assert path.index_at_measured_depth(0) == 0
    assert path.index_at_measured_depth(100) == 1
    assert path.index_at_measured_depth(300) == 1
    with pytest.raises(PhysicsRangeError, match="measured depth = 301"):
        path.index_at_measured_depth(301)
    piece = path.subpath(250, 50)
    assert [s.length for s in piece.sections] == [50, 150]
    assert piece.sections[1].inner_diameter == 0.15
    with pytest.raises(PhysicsRangeError, match="depth interval"):
        path.subpath(-1, 10)


def test_project_trajectory_slices():
    """The bridge example trajectory builds and slices without losing length."""
    data = Path(__file__).parents[3] / "examples/legacy/gemini_project_bridge/old_project"
    table = pd.read_csv(data / "well_trajectory.csv", sep=";").to_dict("records")
    path = geometry.build_path(table)
    assert path.total_length == 2800
    assert path.subpath(600, 2800).total_length + path.subpath(0, 600).total_length == 2800
    assert path.index_at_measured_depth(600) == 2


def test_mean_velocity_by_hand():
    """Velocity is m / (rho A): the flow of 1 m/s in a 0.1 m water pipe, sign kept."""
    area = math.pi * 0.1**2 / 4
    assert geometry.mean_velocity(1000 * area, 1000.0, 0.1) == pytest.approx(1.0)
    assert geometry.mean_velocity(-1000 * area, 1000.0, 0.1) == pytest.approx(-1.0)


def test_mean_velocity_matches_on_arrays():
    """The velocity runs on arrays as on floats for forward, reverse and zero flow."""
    rows = [(flow, 1000.0, 0.1778) for flow in (10.0, -10.0, 0.0)]
    assert_function_matches(geometry.mean_velocity, rows)
