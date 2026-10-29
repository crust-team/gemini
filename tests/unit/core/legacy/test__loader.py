"""Interpretation of a parsed old project as converted designs, bindings and boundary data."""

import json
import shutil
import warnings
from pathlib import Path

import pytest

import gemini as gm
from gemini.core.legacy._loader import load_legacy_design, node_kinds
from gemini.errors import GeminiWarning, LegacyFormatError

OLD = Path(__file__).parents[4] / "examples/legacy/gemini_project_bridge/old_project"


@pytest.fixture(scope="module")
def project():
    """Parse the example old project once; tests copy it before editing."""
    return gm.legacy.read_project(OLD)


def _copy(tmp_path):
    folder = tmp_path / "old"
    shutil.copytree(OLD, folder)
    return folder


def _edit_param(folder, name, edit):
    path = folder / f"{name}.param"
    raw = json.loads(path.read_text(encoding="utf-8"))
    edit(raw)
    path.write_text(json.dumps(raw), encoding="utf-8")


def test_design_maps_every_node_and_the_riser(project):
    """Every old node becomes one plant path; the buried ESP splits the production well."""
    design = load_legacy_design(project)
    assert set(design.modules) == set(gm.legacy.tables.NODE_PATHS.values()) | {"doublet.riser"}
    assert design.modules["doublet.riser"].params[0].params["segment"] == "above_esp"
    assert design.modules["doublet.well"].params[0].params["esp_depth"] == 600
    assert design.bindings["filters.hot"].measured["pressure_drop"].column == "FilterA_PDrop"
    assert design.boundary["stream_defaults"] == {"heat_exchanger": {"cold_in": {"p": 5e5}}}
    assert design.unmapped == []


def test_node_kinds_infer_reservoir_roles(project):
    """A reservoir with an incoming link is the injection side."""
    kinds = {project.nodes[node_id].name: kind for node_id, kind in node_kinds(project).items()}
    assert kinds["reservoir_c1b5"] == "production_reservoir"
    assert kinds["reservoir_28fc"] == "injection_reservoir"
    assert kinds["esp_1ee3"] == "esp"


def test_neighbour_parameters_compare_parsed_times(tmp_path):
    """Neighbour snapshots match by instant, whatever the timestamp spelling."""

    def iso_times(raw):
        raw["parameters"]["timestamps"] = ["2020-01-01T00:00:00"]

    folder = _copy(tmp_path)
    _edit_param(folder, "esp_1ee3", iso_times)
    design = load_legacy_design(gm.legacy.read_project(folder))
    assert design.modules["doublet.well"].params[0].params["esp_depth"] == 600


def test_unmapped_fields_warn_once(tmp_path):
    """Unknown properties and measured tags are listed in one warning by to_plant."""

    def add_unknown(raw):
        raw["parameters"]["property"]["esp_colour"] = ["red"]
        raw["tagnames"]["measured"]["esp_noise"] = ["Noise"]

    folder = _copy(tmp_path)
    _edit_param(folder, "esp_1ee3", add_unknown)
    project = gm.legacy.read_project(folder)
    assert load_legacy_design(project).unmapped == [
        "esp_1ee3.parameters.esp_colour",
        "esp_1ee3.tagnames.measured.esp_noise",
    ]
    from examples.shared.doublet_heat.plant import DoubletHeatPlant

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        gm.legacy.to_plant(project, DoubletHeatPlant())
    assert len(caught) == 1 and issubclass(caught[0].category, GeminiWarning)
    assert "esp_colour" in str(caught[0].message) and "esp_noise" in str(caught[0].message)


def test_unknown_nodes_are_rejected(tmp_path, project):
    """The bridge maps exactly the example node table and names the differences."""
    edited = project.model_copy(deep=True)
    node_id = next(iter(edited.nodes))
    edited.nodes[node_id] = edited.nodes[node_id].model_copy(update={"name": "boiler_1"})
    with pytest.raises(LegacyFormatError, match="boiler_1"):
        load_legacy_design(edited)
