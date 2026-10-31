"""Results as one ``.npz`` archive: typed arrays for numeric columns, JSON text for the rest.

A column that is a float, integer or boolean array is stored as that array, so every bit
survives. Any other column (lists, strings, ``None``, mixed cells) is one JSON text holding the
list of its cells; Python writes floats in JSON with the shortest text that reads back as the
same number. The metadata is one JSON text too, so the archive loads with ``allow_pickle=False``.
"""

import io
import json
import zipfile

import numpy as np
import pandas as pd

from gemini._utils.version import OLDEST_READABLE, is_older, package_version
from gemini.errors import ValidationError

TIME_NAME = "time"
METADATA_NAME = "metadata"


def _plain_cell(value):
    """Return a NumPy scalar or array found inside a cell as plain Python."""
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    raise ValidationError(f"results cell = {value!r}; expected a JSON-like value")


def _is_typed(series):
    """Whether a column is a NumPy float, integer or boolean array."""
    dtype = series.dtype
    return isinstance(dtype, np.dtype) and dtype.kind in "fiub"


def pack(frame, metadata):
    """Return the arrays of a table (``(path, field)`` columns, UTC time index) and its metadata."""
    arrays = {TIME_NAME: frame.index.asi8}
    columns = []
    for position, (path, field) in enumerate(frame.columns):
        series = frame.iloc[:, position]
        name = f"column_{position}"
        if _is_typed(series):
            arrays[name] = series.to_numpy()
        else:
            arrays[name] = np.array(json.dumps(series.tolist(), default=_plain_cell))
        columns.append([path, field, name])
    described = dict(
        metadata, version=package_version(), time_unit=frame.index.unit, columns=columns
    )
    arrays[METADATA_NAME] = np.array(json.dumps(described))
    return arrays


def to_file(file, frame, metadata):
    """Write the archive of a table to a path or a binary file object."""
    np.savez(file, **pack(frame, metadata))


def to_bytes(frame, metadata):
    """Return the archive of a table as bytes."""
    buffer = io.BytesIO()
    to_file(buffer, frame, metadata)
    return buffer.getvalue()


def from_file(file):
    """Return ``(times, columns, metadata)`` of an archive path or binary file object.

    ``times`` is a UTC ``DatetimeIndex``; ``columns`` lists ``(path, field, values)`` with a NumPy
    array or a list of cells. Anything that is not a results archive raises ``ValidationError``.
    """
    try:
        with np.load(file, allow_pickle=False) as archive:
            stored = {name: archive[name] for name in archive.files}
        metadata = json.loads(str(stored[METADATA_NAME]))
    except (ValueError, OSError, KeyError, zipfile.BadZipFile) as error:
        raise ValidationError(
            f"results archive: {error}; expected a .npz written by Results.save",
            code="invalid_format",
        ) from error
    _check_version(metadata)
    times = _times(stored[TIME_NAME], metadata["time_unit"])
    columns = [(path, field, _cells(stored[name])) for path, field, name in metadata["columns"]]
    return times, columns, metadata


def _check_version(metadata):
    """Refuse an archive written before the oldest readable version."""
    if is_older(metadata.get("version")):
        raise ValidationError(
            f"results archive: version = {metadata.get('version')!r}; expected a file written "
            f"by gemini {OLDEST_READABLE} or later",
            path="version",
            code="old_format",
        )


def _times(values, unit):
    """Return the tick times stored as integers of ``unit`` since the epoch, as UTC."""
    index = pd.DatetimeIndex(values.view(f"M8[{unit}]")).tz_localize("UTC")
    return index.rename("timestamp")


def _cells(stored):
    """Return a stored column: a numeric array as it is, a JSON text as its list of cells."""
    if stored.dtype.kind == "U":
        return json.loads(str(stored))
    return stored
