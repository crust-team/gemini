"""Loader alignment, gaps and chunked reads."""

from datetime import timedelta

import numpy as np
import pandas as pd
import pytest

import gemini as gm
from gemini.engine.loader import Loader
from tests.fixtures.errors import raises


@pytest.fixture
def source():
    """Twelve 15-minute rows with a numeric value and a text flag."""
    index = pd.date_range("2024-01-01", periods=12, freq="15min", tz="UTC")
    frame = pd.DataFrame({"v": range(12), "status": ["Normal"] * 11 + ["Alarm"]}, index=index)
    return gm.Dataset.from_frame(frame)


def test_mean_bins_use_the_clock_durations(source):
    """Hourly means are hand-checkable; the final bin uses the clock's one-hour step."""
    clock = gm.engine.Clock.range(source.start, source.end, "1h")
    rows = list(Loader(source, clock.ticks, align="mean", durations=clock.durations))
    assert [sample.row["v"] for sample in rows] == [1.5, 5.5, 9.5]
    assert rows[-1].row["status"] == "Alarm"
    assert [sample.dt for sample in rows] == [3600.0] * 3


def test_previous_holds_until_max_gap_and_exact_needs_a_row(source):
    """Stale previous rows become NaN; exact alignment only accepts rows at the tick."""
    index = source.to_frame().index
    sparse = gm.Dataset.from_frame(source.to_frame().drop(index[1:8]))
    ticks = gm.engine.Clock.range(index[0], index[-1], "15min").ticks
    rows = list(Loader(sparse, ticks, max_gap=timedelta(minutes=30)))
    assert [sample.row["v"] for sample in rows[:3]] == [0, 0, 0]
    assert np.isnan(rows[3].row["v"]) and np.isnan(rows[3].row["status"])
    assert rows[8].row["v"] == 8
    exact = list(Loader(sparse, ticks, align="exact", max_gap=timedelta(hours=3)))
    assert exact[0].row["v"] == 0 and np.isnan(exact[1].row["v"])


def test_chunks_and_default_durations(source):
    """Small chunks give the same samples; without durations the native step ends the clock."""
    ticks = source.to_frame().index
    whole = list(Loader(source, ticks))
    chunked = list(Loader(source, ticks, chunk=timedelta(minutes=40)))
    assert [(s.t, s.dt, s.row) for s in chunked] == [(s.t, s.dt, s.row) for s in whole]
    assert whole[-1].dt == 900.0


@pytest.mark.parametrize("unit", ["s", "ms", "us", "ns"])
def test_alignment_is_independent_of_the_timestamp_resolution(source, unit):
    """Indexes and ticks in any resolution sample alike; pandas 3 parses text as microseconds."""
    frame = source.to_frame()
    frame.index = frame.index.as_unit(unit)
    data = gm.Dataset(frame)
    assert data.native_step == timedelta(minutes=15)
    for ticks in (frame.index, frame.index.as_unit("ns")):
        for align in ("previous", "exact"):
            rows = list(Loader(data, ticks, align=align))
            assert [sample.row["v"] for sample in rows] == list(range(12))
            assert [sample.dt for sample in rows] == [900.0] * 12
    sparse = gm.Dataset(frame.drop(frame.index[1:8]))
    rows = list(Loader(sparse, frame.index, max_gap=timedelta(minutes=30)))
    assert [sample.row["v"] for sample in rows[:3]] == [0, 0, 0]
    assert np.isnan(rows[3].row["v"]) and rows[8].row["v"] == 8
    clock = gm.engine.Clock.range(source.start, source.end, "1h")
    hourly = clock.ticks.as_unit(unit)
    means = list(Loader(data, hourly, align="mean", durations=clock.durations))
    assert [sample.row["v"] for sample in means] == [1.5, 5.5, 9.5]


def test_options_and_columns_are_validated(source):
    """Invalid options fail at construction; unknown columns fail on the first read."""
    with pytest.raises(gm.errors.RunError, match="align = 'nearest'"):
        Loader(source, source.to_frame().index, align="nearest")
    with pytest.raises(gm.errors.RunError, match="chunk"):
        Loader(source, source.to_frame().index, chunk=timedelta(0))
    with raises(gm.errors.RunError, "invalid_data", match="absent_a, absent_b"):
        list(Loader(source, source.to_frame().index, columns=["absent_b", "absent_a"]))


def _same_as_iteration(loader):
    """Assert ``arrays()`` holds exactly the times, durations and values iteration yields."""
    samples = list(loader)
    aligned = loader.arrays()
    assert aligned.times == [sample.t for sample in samples]
    assert aligned.durations.tolist() == [sample.dt for sample in samples]
    assert list(aligned.columns) == list(loader.columns)
    for name, values in aligned.columns.items():
        expected = [sample.row[name] for sample in samples]
        assert len(values) == len(expected)
        for actual, wanted in zip(values.tolist(), expected):
            assert (actual == wanted) or (pd.isna(actual) and pd.isna(wanted))


@pytest.mark.parametrize("align", ["previous", "exact", "mean"])
@pytest.mark.parametrize("chunk", [timedelta(days=7), timedelta(minutes=40)])
def test_arrays_equal_iteration_with_gaps_and_chunks(source, align, chunk):
    """Gaps, ``max_gap``, text columns, chunk borders and every alignment agree with iteration."""
    index = source.to_frame().index
    sparse = gm.Dataset.from_frame(source.to_frame().drop(index[1:8]))
    ticks = gm.engine.Clock.range(
        index[0] - timedelta(hours=1), index[-1] + timedelta(hours=2), "15min"
    )
    for max_gap in (None, timedelta(minutes=30), timedelta(hours=3)):
        loader = Loader(sparse, ticks.ticks, align=align, max_gap=max_gap, chunk=chunk)
        _same_as_iteration(loader)


def test_arrays_of_numeric_columns_are_floats_and_cover_empty_reads(source):
    """Numeric data gives float arrays; ticks far from the data give all-gap arrays."""
    numeric = gm.Dataset.from_frame(source.to_frame()[["v"]])
    ticks = gm.engine.Clock.range(numeric.start, numeric.end, "15min").ticks
    assert Loader(numeric, ticks).arrays().columns["v"].dtype == np.float64
    far = pd.date_range("2030-01-01", periods=3, freq="15min", tz="UTC")
    aligned = Loader(numeric, far).arrays()
    assert np.isnan(aligned.columns["v"]).all()
    _same_as_iteration(Loader(numeric, far))
    assert Loader(numeric, []).arrays().times == []


@pytest.mark.parametrize("align", ["previous", "exact", "mean"])
def test_samples_are_built_from_the_arrays(source, align):
    """Iterating gives the rows of ``arrays()``, for every alignment: there is one alignment."""
    ticks = source.to_frame().index[::2]
    loader = Loader(source, ticks, align=align, chunk=timedelta(minutes=70))
    aligned = loader.arrays()
    samples = list(loader)
    assert [sample.t for sample in samples] == aligned.times
    assert [sample.dt for sample in samples] == aligned.durations.tolist()
    for index, sample in enumerate(samples):
        for column in loader.columns:
            expected = aligned.columns[column][index]
            assert sample.row[column] == expected or (expected != expected)


def test_numbers_and_present_apply_the_missing_rule_once(source):
    """Text and NaN are not present; numbers convert to floats."""
    sparse = gm.Dataset.from_frame(source.to_frame().drop(source.to_frame().index[2:4]))
    ticks = source.to_frame().index[:6]
    aligned = Loader(sparse, ticks, align="exact", max_gap=timedelta(hours=1)).arrays()
    assert aligned.present("v").tolist() == [True, True, False, False, True, True]
    assert np.isnan(aligned.numbers("status")).all()
    assert aligned.numbers("v")[:2].tolist() == [0.0, 1.0]
