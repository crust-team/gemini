"""Converting an old project folder to a plant spec."""

import gemini as gm
from gemini.modules.plants import legacy_project
from gemini.utils.files import read_json
from tests.fixtures import OLD_PROJECT, SHARED
from tests.fixtures.errors import raises


def test_the_example_project_converts_to_the_shared_plant_file():
    """The old example project gives the spec of the shared doublet heat plant, exactly."""
    spec = legacy_project.convert_legacy(OLD_PROJECT)
    assert spec == read_json(SHARED / "plant.json")
    assert gm.plants.validate(spec) == []
    assert gm.plants.from_spec(spec).to_spec() == spec


def test_the_public_name_is_the_same_function():
    """``gm.plants.convert_legacy`` is this function."""
    assert gm.plants.convert_legacy is legacy_project.convert_legacy


def test_a_folder_without_a_diagram_is_a_legacy_format_error(tmp_path):
    """A folder that is not an old project raises the legacy error, naming the missing file."""
    with raises(gm.errors.ValidationError, "invalid_format", match="diagram"):
        legacy_project.convert_legacy(tmp_path)
