"""Run every numbered example as a user would, without external services.

Examples resolve their shared data as ``examples/...`` relative to the working directory and
write generated output below ``runs/``. Each one runs in its own ``tmp_path`` that links
``examples`` to the repository copy, so shared paths resolve unchanged while all output stays
in the temporary directory.
"""

import os
import subprocess
import sys

import pytest

from tests.fixtures import ROOT

pytestmark = pytest.mark.e2e
EXAMPLES = sorted((ROOT / "examples").rglob("*.py"))
TIMEOUT_S = 900
"""Hang guard per example, not a speed limit: the full-year module API example takes 110-180 s
on 4-vCPU CI runners beside the other release-profile workers, and that profile has no budget."""


@pytest.mark.parametrize("path", EXAMPLES, ids=[str(path.relative_to(ROOT)) for path in EXAMPLES])
def test_example(path, dataset_path, tmp_path):
    """Examples load the checked-in dataset, execute cleanly and produce useful output."""
    (tmp_path / "examples").symlink_to(ROOT / "examples", target_is_directory=True)
    (tmp_path / "datasets").symlink_to(ROOT / "datasets", target_is_directory=True)
    env = os.environ.copy()
    env["GEMINI_EXAMPLE_DATASET"] = str(dataset_path)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, (str(ROOT), env.get("PYTHONPATH"))))
    completed = subprocess.run(
        [sys.executable, str(path)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=TIMEOUT_S,
        env=env,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip()
