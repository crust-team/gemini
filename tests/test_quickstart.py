"""Execute the exact acceptance script from the example."""

import runpy
from pathlib import Path

import pandas as pd


def test_quickstart(tmp_path, monkeypatch):
    """Run unchanged user calls in an isolated output directory and verify their products."""
    root = Path(__file__).parents[1]
    (tmp_path / "datasets").symlink_to(root / "datasets", target_is_directory=True)
    monkeypatch.chdir(tmp_path)
    values = runpy.run_path(str(root / "examples/00_quickstart.py"))
    assert len(values["res"]) == 17280
    pd.testing.assert_frame_equal(
        values["res"].to_frame(), values["res2"].to_frame(), check_exact=True
    )
    assert len(values["sim"]) == 24 and not values["sim"].errors
    assert values["fit"].success and values["fit"].applied
    assert len(values["out"]) == 97
