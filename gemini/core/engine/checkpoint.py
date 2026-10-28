"""Versioned checkpoint manifests with atomic publication of complete result generations."""

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Checkpoint(BaseModel):
    """Portable engine state; the manifest points to an immutable sibling result generation."""

    model_config = ConfigDict(extra="forbid")
    version: Literal[1] = 1
    run_kind: Literal["simulate", "replay", "live"] | None = None
    plant: dict
    module_states: dict[str, Any] = Field(default_factory=dict)
    clock: dict | None = None
    position: datetime | None = None
    dataset: dict | None = None
    results_file: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    only: list[str] | None = None
    on_error: Literal["record", "raise"] = "record"


def save(path, checkpoint, results):
    """Publish results first and atomically replace the manifest last.

    Generation filenames ensure a crash cannot pair an old manifest with newer results.
    Previous generations are removed only after a successful manifest replacement.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    previous = load(path).results_file if path.exists() else None
    generation = uuid.uuid4().hex
    if results is not None:
        target = path.with_name(path.name + ".results." + generation)
        result_path = results.save(target)
        checkpoint.results_file = result_path.name
        for file in (result_path, Path(str(result_path) + ".json")):
            with file.open("rb") as handle:
                os.fsync(handle.fileno())
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


def load(path):
    """Validate the version and prevent sibling result paths from escaping the checkpoint folder."""
    checkpoint = Checkpoint.model_validate(json.loads(Path(path).read_text()))
    if checkpoint.results_file and Path(checkpoint.results_file).name != checkpoint.results_file:
        raise ValueError("Checkpoint results_file must name a sibling file")
    return checkpoint
