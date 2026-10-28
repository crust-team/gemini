"""Run the documented PyTorch-style module API acceptance script unchanged."""

import runpy
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e


def test_module_api():
    """Execute the checked-in acceptance script from the repository root."""
    root = Path(__file__).parents[2]
    runpy.run_path(root / "examples/core/basics/01_module_api.py", run_name="__main__")
