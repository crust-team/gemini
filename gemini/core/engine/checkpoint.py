"""Versioned checkpoint manifests with atomic publication of complete result generations."""

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from gemini.core.data.dataset import Dataset
from gemini.errors import CheckpointError
from gemini.utils.files import read_cells, read_json, write_cells


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
    runtime: dict[str, Any] = Field(default_factory=dict)


def _fsync(*paths):
    """Flush written files, or a folder after a rename, to the storage device."""
    for path in paths:
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def _write_dataset(path, dataset, max_gap):
    """Write unfinished rows, their unit metadata and the run's ``max_gap``, then flush them.

    The names are unique per generation and unreferenced until the manifest is replaced, so the
    files are written in place.
    """
    units = {name: info.model_dump(mode="json") for name, info in dataset.columns.items()}
    gap = str(max_gap) if max_gap is not None else None
    write_cells(path, dataset.to_frame(), {"units": units, "max_gap": gap}, index_label="time")
    _fsync(path, Path(str(path) + ".json"))


def read_dataset(path):
    """Return the checkpoint-owned rows and the stored ``max_gap`` (None when not recorded)."""
    frame, metadata = read_cells(path)
    frame.index = pd.to_datetime(frame.index, utc=True)
    gap = metadata.get("max_gap")
    return (
        Dataset.from_frame(frame, units=metadata.get("units")),
        pd.Timedelta(gap) if gap is not None else None,
    )


def save(path, checkpoint, results, remaining_data=None, max_gap=None):
    """Publish results and data first and atomically replace the manifest last.

    Generation filenames ensure a crash cannot pair an old manifest with newer results.
    Previous generations are removed only after a successful manifest replacement. Every save
    rewrites all unfinished rows, so frequent automatic checkpoints of a long run cost time
    proportional to the remaining rows each time.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    old = load(path) if path.exists() else None
    generation = uuid.uuid4().hex
    if results is not None:
        result_path = results.save(path.with_name(path.name + ".results." + generation))
        checkpoint.results_file = result_path.name
        _fsync(result_path, Path(str(result_path) + ".json"))
    if remaining_data is not None and len(remaining_data):
        data_path = path.with_name(path.name + ".data." + generation + ".csv")
        _write_dataset(data_path, remaining_data, max_gap)
        checkpoint.remaining_data_file = data_path.name
    _publish(path, checkpoint, generation)
    if old is not None:
        _remove_unreferenced(path.parent, old, checkpoint)


def _publish(path, checkpoint, generation):
    """Write the manifest to a temporary sibling, flush it and rename it over ``path``."""
    temporary = path.with_name(path.name + "." + generation + ".tmp")
    try:
        with temporary.open("w") as handle:
            handle.write(checkpoint.model_dump_json(indent=2) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _remove_unreferenced(folder, old, checkpoint):
    """Delete the previous generation's files that the new manifest no longer names."""
    for field in ("results_file", "remaining_data_file"):
        previous = getattr(old, field)
        if previous and previous != getattr(checkpoint, field):
            (folder / previous).unlink(missing_ok=True)
            (folder / (previous + ".json")).unlink(missing_ok=True)


def load(path):
    """Validate the version and prevent sibling result paths from escaping the checkpoint folder."""
    try:
        checkpoint = Checkpoint.model_validate(read_json(path))
    except ValidationError as exc:
        raise CheckpointError(
            f"{path}: manifest is invalid; expected a version-1 checkpoint\n{exc}"
        ) from exc
    for field in ("results_file", "remaining_data_file"):
        value = getattr(checkpoint, field)
        if value and Path(value).name != value:
            raise CheckpointError(f"{path}: {field} = {value!r}; expected a sibling file name")
    return checkpoint
