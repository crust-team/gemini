"""Immutable reference values, their generators and shared test paths."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests/fixtures"
SHARED = ROOT / "examples/shared/doublet_heat"
OLD_PROJECT = ROOT / "examples/legacy/gemini_project_bridge/old_project"
