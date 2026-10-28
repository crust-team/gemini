"""Run every documented example without external services."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
pytestmark = pytest.mark.e2e


@pytest.mark.parametrize(
    "path",
    [
        path
        for path in sorted((ROOT / "examples").glob("**/[0-9][0-9]_*.py"))
        if path.name != "01_module_api.py"
    ],
    ids=str,
)
def test_example(path, dataset_path):
    """Examples load the checked-in dataset, execute cleanly and produce useful output."""
    env = os.environ.copy()
    env["GEMINI_EXAMPLE_DATASET"] = str(dataset_path)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, (str(ROOT), env.get("PYTHONPATH"))))
    completed = subprocess.run(
        [sys.executable, str(path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=180,
        env=env,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip()
