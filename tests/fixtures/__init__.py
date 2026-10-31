"""Immutable reference values, their generators and shared test paths."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests/fixtures"
SHARED = ROOT / "datasets/doublet_heat"
OLD_PROJECT = ROOT / "datasets/legacy_project"
