"""Checkpoint manifests: publication, sibling files and load validation."""

import json

import pandas as pd
import pytest

import gemini as gm
from gemini.engine import checkpoint as storage
from gemini.engine.results import Results


def manifest(**fields):
    """Return a minimal valid manifest."""
    return storage.Checkpoint(plant_class="module:Plant", plant={}, **fields)


def test_save_publishes_generations_and_removes_the_previous_one(tmp_path):
    """Rows and their max_gap round trip; an older generation's files are deleted."""
    path = tmp_path / "run.ckpt"
    index = pd.date_range("2024-01-01", periods=2, freq="15min", tz="UTC")
    rows = gm.Dataset.from_frame(
        pd.DataFrame({"x": [0.1 + 0.2, 2.0]}, index=index), units={"x": "W"}
    )
    storage.save(path, manifest(), Results(), rows, pd.Timedelta(minutes=30))
    first = storage.load(path)
    data, max_gap = storage.read_dataset(tmp_path / first.remaining_data_file)
    assert data.fingerprint() == rows.fingerprint()
    assert max_gap == pd.Timedelta(minutes=30)
    storage.save(path, manifest(), Results())
    second = storage.load(path)
    assert second.remaining_data_file is None
    names = {file.name for file in tmp_path.iterdir()}
    assert first.remaining_data_file not in names and first.results_file not in names
    assert second.results_file in names


def test_load_rejects_escaping_sibling_paths_and_invalid_manifests(tmp_path):
    """Sibling names must stay in the folder; another manifest fails as CheckpointError."""
    path = tmp_path / "bad.ckpt"
    path.write_text(manifest(results_file="../outside.csv").model_dump_json())
    with pytest.raises(gm.errors.CheckpointError, match="results_file = '../outside.csv'"):
        storage.load(path)
    data = json.loads(manifest().model_dump_json()) | {"backend": 2}
    path.write_text(json.dumps(data))
    with pytest.raises(gm.errors.CheckpointError, match="manifest is invalid"):
        storage.load(path)


@pytest.mark.parametrize("version", [1, 2, None, "0.0.9"])
def test_a_checkpoint_written_before_the_oldest_version_does_not_load(tmp_path, version):
    """The former integer versions and anything before 0.1.0 raise with the code old_format."""
    path = tmp_path / "old.ckpt"
    path.write_text(json.dumps(json.loads(manifest().model_dump_json()) | {"version": version}))
    with pytest.raises(gm.errors.ValidationError, match="version = ") as caught:
        storage.load(path)
    assert caught.value.code == "old_format"


def test_a_checkpoint_records_the_package_version():
    """The manifest holds ``gm.__version__``."""
    assert manifest().version == gm.__version__
