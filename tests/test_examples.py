"""Run every documented example without external services."""

import runpy
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "path", sorted((Path(__file__).parents[1] / "examples").glob("[0-9]*.py")), ids=lambda p: p.name
)
def test_example(path, capsys):
    """Examples load the checked-in dataset, execute cleanly and produce useful output."""
    runpy.run_path(str(path), run_name="__main__")
    assert capsys.readouterr().out.strip()
