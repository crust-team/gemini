"""Run the documented PyTorch-style module API acceptance script unchanged."""

import runpy
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e


def test_module_api(monkeypatch, dataset_path):
    """Execute the checked-in acceptance script from the repository root."""
    root = Path(__file__).parents[2]
    monkeypatch.setenv("GEMINI_EXAMPLE_DATASET", str(dataset_path))
    runpy.run_path(root / "examples/core/basics/01_module_api.py", run_name="__main__")
