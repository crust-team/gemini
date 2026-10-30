"""Result access, unit conversion, summaries, JSON views, slices and lossless files."""

import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

import gemini as gm
from gemini.core.engine.chunks import PathColumns, ResultChunk
from gemini.core.engine.results import Results
from gemini.core.types import Health, ModuleResult, Values


def result(**outputs):
    """Return a minimal module result with the given outputs."""
    return ModuleResult(outputs=Values(outputs), outlets=gm.Ports({}))


def commit(rows, time, path, outputs, health, dt, skips):
    """Commit one tick of one path: its outputs and health as columns of one entry."""
    table = PathColumns.of(
        result(**{name: np.array([value]) for name, value in outputs.items()}),
        health,
        np.ones(1, dtype=bool),
    )
    rows.commit(ResultChunk([time], [dt], {path: table}, [skips]))


def results():
    """Return two rows: one pump with power and electricity, one skip."""
    rows = Results()
    times = [datetime(2024, 1, 1, hour, tzinfo=timezone.utc) for hour in (0, 1)]
    health = Health(score=1, alarm=True, message="low")
    for time, power in zip(times, (1000.0, 3000.0)):
        commit(
            rows,
            time,
            "pump",
            dict(head=2e5, electricity=power),
            health,
            3600.0,
            {"pump": {"pump.suction.p": 1}},
        )
    return rows


def test_empty_results_summary():
    """An empty finite run has an empty summary."""
    assert Results().energy_report().empty and Results().summary() == {}


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
    summary = results().energy_report()
    row = summary.loc[("pump", "electricity")]
    assert row["energy_J"] == 4000.0 * 3600
    assert row["peak_W"] == 3000.0 and row["alarms"] == 2 and row["skipped"] == 2
    assert row["reasons"] == {"pump.suction.p": 2}


def test_slice_and_lossless_files(tmp_path):
    """A slice keeps its own skips; saved results load with identical cells and summary."""
    rows = results()
    tail = rows.slice(1)
    assert len(tail) == 1 and tail.skip_counts == {"pump": {"pump.suction.p": 1}}
    path = rows.save(tmp_path / "results.npz")
    loaded = Results.load(path)
    pd.testing.assert_frame_equal(loaded.to_frame(), rows.to_frame())
    pd.testing.assert_frame_equal(loaded.energy_report(), rows.energy_report())


def with_units():
    """Return the two-row pump results with the units a plant would declare."""
    rows = results()
    rows.units = {"pump": {"head": "Pa", "electricity": "W"}}
    return rows


def test_names_lists_every_readable_field_by_path():
    """names() maps each path to its fields, in column order."""
    names = with_units().names()
    assert list(names) == ["pump"] and names["pump"][:2] == ["head", "electricity"]
    assert "health_score" in names["pump"] and Results().names() == {}


def test_get_returns_time_values_and_unit_as_json():
    """get() gives ISO times, plain values and the SI unit; windows are inclusive."""
    rows = with_units()
    series = rows.get("pump", "electricity")
    assert series == {
        "time": ["2024-01-01T00:00:00+00:00", "2024-01-01T01:00:00+00:00"],
        "values": [1000.0, 3000.0],
        "unit": "W",
    }
    json.dumps(series, allow_nan=False)
    late = rows.get("pump", "head", start="2024-01-01T01:00:00Z")
    assert late["time"] == ["2024-01-01T01:00:00+00:00"] and late["values"] == [2e5]
    assert rows.get("pump", "operating", end=datetime(2024, 1, 1, tzinfo=timezone.utc))[
        "values"
    ] == [True]
    assert rows.get("pump", "health_score")["unit"] == "-"
    with pytest.raises(gm.errors.UnknownResultError, match="did you mean 'head'"):
        rows.get("pump", "heads")
    with pytest.raises(gm.errors.UnknownResultError, match="did you mean 'pump'") as caught:
        rows.get("pumps", "head")
    assert caught.value.suggestions == ("pump",)


def test_summary_reports_min_max_mean_and_unit_per_numeric_field():
    """summary() covers numeric fields only, for one path and for a window."""
    rows = with_units()
    summary = rows.summary()
    assert summary["pump"]["electricity"] == {
        "min": 1000.0,
        "max": 3000.0,
        "mean": 2000.0,
        "unit": "W",
    }
    assert "operating" not in summary["pump"] and "health_message" not in summary["pump"]
    assert (
        rows.summary("pump", start="2024-01-01T01:00:00Z")["pump"]["electricity"]["min"] == 3000.0
    )
    json.dumps(summary, allow_nan=False)
    with pytest.raises(gm.errors.UnknownResultError):
        rows.summary("pumps")


def test_errors_list_failed_and_skipped_rows_with_their_codes():
    """Each row has a timestamp, module, code, type and message; skips use missing_value."""
    rows = with_units()
    rows.commit(
        ResultChunk(
            [datetime(2024, 1, 1, 2, tzinfo=timezone.utc)],
            [3600.0],
            {},
            [{"pump": {"pump.suction.p": 1}}],
            [(0, dict(module="pump", message="boom", type="ValueError", code="module_error"))],
        )
    )
    errors = rows.errors()
    assert [row["code"] for row in errors] == ["missing_value"] * 2 + [
        "module_error",
        "missing_value",
    ]
    assert errors[2] == {
        "timestamp": "2024-01-01T02:00:00+00:00",
        "module": "pump",
        "code": "module_error",
        "type": "ValueError",
        "message": "boom",
    }
    assert errors[0]["message"] == "pump.suction.p"
    assert {row["code"] for row in errors} <= set(gm.errors.ROW_CODES)
    json.dumps(errors, allow_nan=False)


def test_to_dict_is_plain_json_with_units():
    """to_dict() holds the time axis, every series with its unit, errors and the end state."""
    rows = with_units()
    rows.end_state = {"position": "2024-01-01T01:00:00+00:00", "module_states": {}}
    data = rows.to_dict()
    json.dumps(data, allow_nan=False)
    assert data["series"]["pump"]["head"] == {"unit": "Pa", "values": [2e5, 2e5]}
    assert data["duration"] == [3600.0, 3600.0] and len(data["time"]) == 2
    assert data["end_state"] == rows.end_state and len(data["errors"]) == 2


def test_files_and_bytes_keep_units_end_state_and_every_cell(tmp_path):
    """A saved or serialised result loads with the same frame, units, errors and end state."""
    rows = with_units()
    rows.end_state = {"position": "2024-01-01T01:00:00+00:00", "module_states": {"a": {"x": 0.1}}}
    for loaded in (
        Results.load(rows.save(tmp_path / "plain")),
        Results.from_bytes(rows.to_bytes()),
    ):
        pd.testing.assert_frame_equal(loaded.to_frame(), rows.to_frame())
        assert loaded.units == rows.units and loaded.end_state == rows.end_state
        assert loaded.errors() == rows.errors() and loaded.skip_counts == rows.skip_counts
        assert loaded.get("pump", "head") == rows.get("pump", "head")
    assert (tmp_path / "plain.npz").exists()


def test_an_archive_needs_no_pickle(tmp_path):
    """Every array of the archive loads with allow_pickle=False, and garbage is refused."""
    path = with_units().save(tmp_path / "results.npz")
    with np.load(path, allow_pickle=False) as archive:
        assert "metadata" in archive.files
        assert all(archive[name].dtype != object for name in archive.files)
    with pytest.raises(gm.errors.ValidationError, match="results archive") as caught:
        Results.from_bytes(b"not an archive")
    assert caught.value.code == "invalid_format"
    old = tmp_path / "old.csv"
    old.write_text("time\n")
    with pytest.raises(gm.errors.ValidationError, match="results archive"):
        Results.load(old)


def test_slices_keep_units_and_end_state():
    """The new rows of a live call read like the whole."""
    rows = with_units()
    rows.end_state = {"position": None, "module_states": {}}
    tail = rows.slice(1)
    assert tail.units == rows.units and tail.end_state == rows.end_state
    assert tail.get("pump", "head")["unit"] == "Pa" and len(tail.errors()) == 1
