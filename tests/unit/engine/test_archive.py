"""The results archive: typed arrays, JSON text for other columns, exact floats and times."""

import io

import numpy as np
import pandas as pd
import pytest

import gemini as gm
from gemini.engine import archive
from gemini.errors import ValidationError


def frame_of(columns):
    """Return a table with (path, field) columns on a three-row UTC index."""
    index = pd.date_range("2024-01-01", periods=3, freq="15min", tz="UTC", unit="us")
    frame = pd.DataFrame(
        {
            position: pd.Series(values, index=index)
            for position, values in enumerate(columns.values())
        }
    )
    frame.columns = pd.MultiIndex.from_tuples(list(columns))
    return frame


def round_trip(frame, metadata=None):
    """Write a table to bytes and read it back: times, columns and metadata."""
    return archive.from_file(io.BytesIO(archive.to_bytes(frame, metadata or {})))


def test_numeric_columns_are_arrays_and_others_json_text():
    """Float, integer and boolean columns keep their dtype; cells of any other kind are JSON."""
    awkward = [0.1, 1 / 3, 1e-300]
    frame = frame_of(
        {
            ("a", "x"): np.array(awkward),
            ("a", "n"): np.array([1, 2, 3]),
            ("a", "ok"): np.array([True, False, True]),
            ("a", "tags"): [[1.5, None], "text", None],
            ("a", "gap"): np.array([np.nan, np.inf, -0.0]),
        }
    )
    times, columns, _ = round_trip(frame)
    by_field = {field: values for _, field, values in columns}
    assert by_field["x"].tolist() == awkward and by_field["n"].dtype == np.int64
    assert by_field["ok"].dtype == bool and by_field["tags"] == [[1.5, None], "text", None]
    assert np.isnan(by_field["gap"][0]) and by_field["gap"][1] == np.inf
    assert np.signbit(by_field["gap"][2])
    assert times.equals(frame.index.rename("timestamp")) and times.dtype == frame.index.dtype


def test_the_time_resolution_survives():
    """A nanosecond index loads as nanoseconds."""
    frame = frame_of({("a", "x"): np.zeros(3)})
    frame.index = frame.index.as_unit("ns") + pd.Timedelta(1, "ns")
    times, _, metadata = round_trip(frame)
    assert times.equals(frame.index.rename("timestamp")) and metadata["time_unit"] == "ns"


def test_a_file_written_before_the_oldest_version_is_refused():
    """A former layout has no version, or one before 0.1.0: the code is old_format."""
    for metadata in ('{"format": 99}', '{"version": "0.0.9"}'):
        buffer = io.BytesIO()
        np.savez(buffer, metadata=np.array(metadata))
        with pytest.raises(ValidationError, match="version = ") as caught:
            archive.from_file(io.BytesIO(buffer.getvalue()))
        assert caught.value.code == "old_format"


def test_an_archive_records_the_package_version():
    """The metadata holds the version that wrote it."""
    assert round_trip(frame_of({("a", "x"): [1.0, 2.0, 3.0]}))[2]["version"] == gm.__version__
