"""JSON files and the lossless JSON-cell table format."""

import numpy as np
import pandas as pd

from gemini._utils.files import (
    decode_cells,
    encode_cell,
    encode_cells,
    from_cells,
    from_json,
    to_cells,
    to_json,
)


def test_json_files_round_trip_with_trailing_newline(tmp_path):
    """Files are indented, end with a newline and create missing folders."""
    path = tmp_path / "nested" / "plant.json"
    to_json(path, {"a": [1, 2]})
    assert path.read_text() == '{\n  "a": [\n    1,\n    2\n  ]\n}\n'
    assert from_json(path) == {"a": [1, 2]}
    to_json(path, {"a": 1}, indent=4)
    assert path.read_text() == '{\n    "a": 1\n}\n'


def test_json_cells_keep_float_bits_lists_flags_and_missing_values(tmp_path):
    """A CSV written from encoded cells decodes to identical values."""
    index = pd.DatetimeIndex(["2024-07-01 00:00", "2024-07-01 00:15"], tz="UTC")
    frame = pd.DataFrame(
        {"x": [0.1 + 0.2, np.nan], "flag": [True, False], "items": [[1.5, 2.0], None]},
        index=index,
    )
    path = tmp_path / "cells.csv"
    encode_cells(frame).to_csv(path, index_label="time")
    read = pd.read_csv(path, index_col="time", dtype=str, keep_default_na=False)
    decoded = decode_cells(read)
    assert decoded["x"].iloc[0] == 0.1 + 0.2
    assert np.isnan(decoded["x"].iloc[1])
    assert decoded["flag"].tolist() == [True, False]
    assert decoded["items"].tolist() == [[1.5, 2.0], None]
    assert list(read.index) == ["2024-07-01T00:00:00+00:00", "2024-07-01T00:15:00+00:00"]


def test_numpy_scalars_encode_as_python_numbers():
    """Integers, booleans and float32 values from NumPy encode like Python numbers."""
    assert encode_cell(np.int64(3)) == "3"
    assert encode_cell(np.bool_(True)) == "true"
    assert encode_cell(np.float32(0.5)) == "0.5"
    assert encode_cell(float("inf")) == "Infinity"


def test_cells_and_their_sidecar_round_trip_through_one_pair_of_functions(tmp_path):
    """``to_cells`` writes a CSV and its JSON sidecar; ``from_cells`` reads both back."""
    index = pd.DatetimeIndex(["2024-07-01 00:00", "2024-07-01 00:15"], tz="UTC")
    frame = pd.DataFrame({"x": [0.1 + 0.2, np.nan], "items": [[1.5, 2.0], None]}, index=index)
    path = tmp_path / "cells.csv"
    to_cells(path, frame, {"note": 1}, index_label="time")
    assert path.read_text().splitlines()[0] == "time,x,items"
    decoded, metadata = from_cells(path)
    assert metadata == {"note": 1}
    assert decoded["x"].iloc[0] == 0.1 + 0.2 and np.isnan(decoded["x"].iloc[1])
    assert decoded["items"].tolist() == [[1.5, 2.0], None]
