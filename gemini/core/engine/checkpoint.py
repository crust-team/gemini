"""Versioned checkpoint manifests with atomic publication of complete result generations."""

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from gemini.core.data.dataset import Dataset


def _encode_cell(value):
    """JSON-encode NumPy-backed pandas scalars without losing float bits."""
    return json.dumps(value.item() if hasattr(value, "item") else value, allow_nan=True)


class Checkpoint(BaseModel):
    """Portable engine state; the manifest points to an immutable sibling result generation."""

    model_config = ConfigDict(extra="forbid")
    version: Literal[1] = 1
    run_kind: Literal["simulate", "replay", "live"] | None = None
    plant_class: str
    plant: dict
    module_states: dict[str, Any] = Field(default_factory=dict)
    clock: dict | None = None
    position: datetime | None = None
    dataset_fingerprint: str | None = None
    remaining_data_file: str | None = None
    results_file: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    only: list[str] | None = None
    on_error: Literal["record", "raise"] = "record"


def _write_dataset(path, dataset):
    """Atomically write remaining in-memory rows and their unit/dtype metadata."""
    frame = dataset.to_frame()
    temporary = path.with_name(path.name + ".tmp")
    metadata_path = Path(str(path) + ".json")
    metadata_temporary = Path(str(temporary) + ".json")
    encoded = frame.map(_encode_cell)
    encoded.index = [value.isoformat() for value in frame.index]
    encoded.to_csv(temporary, index_label="time")
    metadata_temporary.write_text(
        json.dumps(
            {
                "units": {
                    name: info.model_dump(mode="json") for name, info in dataset.columns.items()
                },
            },
            indent=2,
        )
        + "\n"
    )
    os.replace(temporary, path)
    os.replace(metadata_temporary, metadata_path)


def read_dataset(path):
    """Read a checkpoint-owned CSV dataset without involving a source driver."""
    import pandas as pd

    path = Path(path)
    metadata = json.loads(Path(str(path) + ".json").read_text())
    frame = pd.read_csv(path, index_col="time", dtype=str, keep_default_na=False).map(json.loads)
    frame.index = pd.to_datetime(frame.index, utc=True)
    return Dataset.from_frame(frame, units=metadata.get("units"))


def save(path, checkpoint, results, remaining_data=None):
    """Publish results first and atomically replace the manifest last.

    Generation filenames ensure a crash cannot pair an old manifest with newer results.
    Previous generations are removed only after a successful manifest replacement.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    old = load(path) if path.exists() else None
    previous = old.results_file if old else None
    previous_data = old.remaining_data_file if old else None
    generation = uuid.uuid4().hex
    if results is not None:
        target = path.with_name(path.name + ".results." + generation)
        result_path = results.save(target)
        checkpoint.results_file = result_path.name
        for file in (result_path, Path(str(result_path) + ".json")):
            with file.open("rb") as handle:
                os.fsync(handle.fileno())
    if remaining_data is not None and len(remaining_data):
        data_path = path.with_name(path.name + ".data." + generation + ".csv")
        _write_dataset(data_path, remaining_data)
        checkpoint.remaining_data_file = data_path.name
    temporary = path.with_name(path.name + "." + generation + ".tmp")
    try:
        with temporary.open("w") as handle:
            handle.write(checkpoint.model_dump_json(indent=2) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    if previous and previous != checkpoint.results_file:
        old = path.parent / previous
        old.unlink(missing_ok=True)
        Path(str(old) + ".json").unlink(missing_ok=True)
    if previous_data and previous_data != checkpoint.remaining_data_file:
        old_data = path.parent / previous_data
        old_data.unlink(missing_ok=True)
        Path(str(old_data) + ".json").unlink(missing_ok=True)


def load(path):
    """Validate the version and prevent sibling result paths from escaping the checkpoint folder."""
    checkpoint = Checkpoint.model_validate(json.loads(Path(path).read_text()))
    for field in ("results_file", "remaining_data_file"):
        value = getattr(checkpoint, field)
        if value and Path(value).name != value:
            raise ValueError(f"Checkpoint {field} must name a sibling file")
    return checkpoint
