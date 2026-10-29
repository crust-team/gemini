"""JSON files and the lossless JSON-cell table format used by checkpoints and results."""

import json
from pathlib import Path


def read_json(path):
    """Read one UTF-8 JSON file."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, data, indent=2):
    """Write indented UTF-8 JSON with a trailing newline, creating parent folders."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=indent) + "\n", encoding="utf-8")


def encode_cell(value):
    """JSON-encode one table cell; NumPy scalars become Python numbers without losing bits."""
    return json.dumps(value.item() if hasattr(value, "item") else value, allow_nan=True)


def encode_cells(frame):
    """Return a copy of ``frame`` with JSON-encoded cells and an ISO-8601 timestamp index.

    JSON cells keep lists, flags, missing values and every float bit, which plain CSV does not.
    """
    encoded = frame.map(encode_cell)
    encoded.index = [time.isoformat() for time in frame.index]
    return encoded


def decode_cells(frame):
    """Decode a table written by ``encode_cells`` and read back with every cell as text."""
    return frame.map(json.loads)
