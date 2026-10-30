"""Converting format 1 plant files."""

import copy
import json

import pytest

import gemini as gm
from gemini.errors import PlantFormatError
from tests.fixtures import ROOT

OLD = ROOT / "tests/fixtures/plant_format1.json"
MIGRATED = ROOT / "examples/shared/doublet_heat/plant.json"


@pytest.fixture(scope="module")
def old():
    """Return the stored plant file as the class-based format wrote it."""
    return json.loads(OLD.read_text())


def test_the_old_example_plant_migrates_to_the_stored_spec(old):
    """A tree whose root is a known plant takes its wiring and keeps every stored value."""
    spec = gm.plants.migrate(old)
    assert spec == json.loads(MIGRATED.read_text())
    assert gm.plants.validate(spec) == []
    assert spec["modules"]["doublet"]["params"]["esp.stage_count"] == 15
    assert "thermal_conductance" in spec["modules"]["heat_exchanger"]["params"]
    assert "" in spec["bindings"] and "" in spec["boundary"] and "" in spec["fluids"]


def test_a_current_spec_is_returned_as_a_copy():
    """Migrating format 2 changes nothing."""
    spec = json.loads(MIGRATED.read_text())
    assert gm.plants.migrate(spec) == spec and gm.plants.migrate(spec) is not spec


def test_a_handwritten_root_becomes_flat_dotted_params(old):
    """A class that is not a shipped plant is written as a handwritten root."""
    other = copy.deepcopy(old)
    other["plant_type"] = "tests.fixtures:Booster"
    spec = gm.plants.migrate(other)
    assert spec["type"] == "Booster" and spec["modules"] == {}
    assert spec["params"]["doublet.esp.stage_count"] == 15


def test_a_module_the_wiring_lacks_fails_with_migration_failed(old):
    """The error carries the code and the path of the module."""
    broken = copy.deepcopy(old)
    broken["modules"]["mixer"] = copy.deepcopy(broken["modules"]["degasser"])
    with pytest.raises(PlantFormatError) as caught:
        gm.plants.migrate(broken)
    assert caught.value.code == "migration_failed" and caught.value.path == "mixer"


def test_garbage_fails_with_migration_failed():
    """Things that are not plant files are not crashes."""
    for garbage in ({"version": 1}, {"version": 7}, [], "x"):
        with pytest.raises(PlantFormatError) as caught:
            gm.plants.migrate(garbage)
        assert caught.value.code == "migration_failed"


def test_loading_an_old_file_names_the_migration(old):
    """``from_spec`` of format 1 raises ``old_format``."""
    with pytest.raises(PlantFormatError) as caught:
        gm.plants.from_spec(old)
    assert caught.value.code == "old_format" and "gm.plants.migrate" in str(caught.value)
