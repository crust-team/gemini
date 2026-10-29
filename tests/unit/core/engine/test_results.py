"""Result access, unit conversion, summaries, slices and lossless files."""

from datetime import datetime, timezone

import pandas as pd
import pytest

import gemini as gm
from gemini.core.engine.results import Results
from gemini.core.types import Health, ModuleResult, Values


def result(**outputs):
    """Return a minimal module result with the given outputs."""
    return ModuleResult(outputs=Values(outputs), outlets=gm.Ports({}))


def results():
    """Return two rows: one pump with power and electricity, one skip."""
    rows = Results()
    times = [datetime(2024, 1, 1, hour, tzinfo=timezone.utc) for hour in (0, 1)]
    health = Health(score=1, alarm=True, message="low")
    for time, power in zip(times, (1000.0, 3000.0)):
        rows.append(
            time,
            {"pump": (result(head=2e5, electricity=power), health)},
            3600,
            {"pump": {"pump.suction.p": 1}},
        )
    return rows


def test_empty_results_summary():
    """An empty finite run has an empty summary."""
    assert Results().summary().empty


def test_access_conversion_and_suggestions():
    """Fields are Series; known fields convert units; unknown names suggest a match."""
    rows = results()
    assert rows["pump"].head.tolist() == [2e5, 2e5]
    assert rows["pump"].get("head", unit="bar").tolist() == pytest.approx([2.0, 2.0])
    assert rows["pump"].get("head", unit="barg").tolist() == pytest.approx([2.0, 2.0])
    with pytest.raises(gm.errors.UnknownResultError, match="did you mean 'pump'"):
        rows["pumps"]
    with pytest.raises(gm.errors.UnknownResultError, match="did you mean 'head'"):
        rows["pump"].heads
    with pytest.raises(ValueError, match="for unit conversion"):
        rows["pump"].get("electricity", unit="kW")


def test_summary_integrates_energy_and_counts_alarms_and_skips():
    """Energy is power times dt; alarms and skip reasons are counted per module."""
    summary = results().summary()
    row = summary.loc[("pump", "electricity")]
    assert row["energy_J"] == 4000.0 * 3600
    assert row["peak_W"] == 3000.0 and row["alarms"] == 2 and row["skipped"] == 2
    assert row["reasons"] == {"pump.suction.p": 2}


def test_slice_and_lossless_files(tmp_path):
    """A slice keeps its own skips; saved results load with identical cells and summary."""
    rows = results()
    tail = rows.slice(1)
    assert len(tail) == 1 and tail.skip_counts == {"pump": {"pump.suction.p": 1}}
    path = rows.save(tmp_path / "results.csv")
    loaded = Results.load(path)
    pd.testing.assert_frame_equal(loaded.to_frame(), rows.to_frame())
    pd.testing.assert_frame_equal(loaded.summary(), rows.summary())
