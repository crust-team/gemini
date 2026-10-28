"""Loader sampling and gap tests."""

from datetime import timedelta

import pandas as pd
import pytest

import gemini as gm
from gemini.core.data.loader import Loader


def test_mean_previous_exact_and_gaps():
    """Hourly means are hand-checkable and stale previous rows become missing."""
    index = pd.date_range("2024-01-01", periods=12, freq="15min", tz="UTC")
    source = gm.Dataset.from_frame(
        pd.DataFrame({"v": range(12), "status": ["Normal"] * 12}, index=index)
    )
    clock = gm.Clock.range(index[0], index[-1], "1h")
    assert [sample.row["v"] for sample in Loader(source, clock, align="mean")] == [1.5, 5.5, 9.5]
    sparse = gm.Dataset.from_frame(source.to_frame().drop(index[1:8]))
    rows = list(
        Loader(
            sparse,
            gm.Clock.range(index[0], index[-1], "15min"),
            max_gap=timedelta(minutes=30),
        )
    )
    assert rows[2].row["v"] == 0
    assert rows[3].gap and rows[3].missing == ("v", "status")
    with pytest.raises(ValueError, match="absent_a, absent_b"):
        Loader(source, clock, columns=["absent_b", "absent_a"])
