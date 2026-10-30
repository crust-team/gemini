"""The doublet heat plant built three ways runs bit-identically, on every backend.

The builder, the spec and the migrated old file give the same plant, so their replays are equal
to the last bit (``check_exact``), and the file-based run is the one the committed engine
reference pins in ``test_engine.py``.
"""

import copy

import pandas as pd
import pytest

import gemini as gm
from gemini.core.types.bindings import DatedParams
from gemini.utils.files import read_json
from tests.fixtures import ROOT
from tests.fixtures.parity import BACKENDS, on_each_backend, run_engine

OLD_FILE = ROOT / "tests/fixtures/plant_format1.json"
ROWS = 24


def _add_modules(plant, modules):
    for name, entry in modules.items():
        plant.add(entry["type"], name, **entry.get("params", {}))
        for child, item in entry.get("modules", {}).items():
            plant.add(item["type"], f"{name}.{child}", **item["params"])


def _fill_sections(plant, spec):
    for path, value in spec["fluids"].items():
        plant.get_module(path).fluid = value
    for path, value in spec["boundary"].items():
        plant.get_module(path).boundary = copy.deepcopy(value)
    for path, value in spec["bindings"].items():
        plant.set_bindings(path, value)
    for path, history in spec["param_history"].items():
        plant.get_module(path)._param_history = [DatedParams.model_validate(i) for i in history]


def built_by_hand(spec):
    """Build the doublet heat plant with ``add``, ``connect`` and the setters only."""
    plant = gm.Plant(spec["name"])
    _add_modules(plant, spec["modules"])
    for connection in spec["connections"]:
        plant.connect(connection["source"], connection["target"])
    for name, end in spec["inlets"].items():
        plant.connect(name, end)
    for name, end in spec["outlets"].items():
        plant.connect(end, name)
    _fill_sections(plant, spec)
    return plant


@pytest.fixture(scope="module")
def spec():
    """Return the spec the old file migrates to."""
    return gm.plants.migrate(read_json(OLD_FILE))


@pytest.fixture(scope="module")
def window(fast_frame):
    """Return the first rows of the short window as a dataset."""
    return gm.Dataset.from_frame(fast_frame.iloc[:ROWS], time_column="time")


BUILDERS = {
    "builder": built_by_hand,
    "spec": lambda spec: gm.plants.from_spec(copy.deepcopy(spec)),
    "file": lambda spec: gm.plants.from_dict(copy.deepcopy(spec)),
}


@pytest.fixture(scope="module")
def runs(spec, window):
    """Return the replay and simulate frames of each way of building the plant, per backend."""
    clock = gm.Clock.days(2024, 6, 7)
    first = window.read(window.start, window.start)
    assumed = gm.Dataset.from_frame(pd.DataFrame([first.iloc[0].to_dict()] * 24, index=list(clock)))

    def run(backend):
        return {
            way: (
                run_engine(build(spec), window),
                run_engine(build(spec), assumed, "simulate", clock),
            )
            for way, build in BUILDERS.items()
        }

    return on_each_backend(run)


def test_the_three_ways_give_the_same_plant(spec):
    """Builder, spec and file write the same sections; only the spec states the outputs."""
    by_hand = built_by_hand(spec).to_spec()
    assert gm.plants.from_spec(copy.deepcopy(spec)).to_spec() == spec
    assert by_hand.pop("outputs", None) is None
    assert by_hand == {key: value for key, value in spec.items() if key != "outputs"}


@pytest.mark.parametrize("backend", BACKENDS)
@pytest.mark.parametrize("kind", [0, 1], ids=["replay", "simulate"])
def test_the_three_ways_run_bit_identically(runs, backend, kind):
    """Spec and file are the same frame; the builder's columns equal the spec's, bit for bit."""
    frames = {way: pair[kind].frame for way, pair in runs[backend].items()}
    assert len(frames["spec"]) == ROWS
    pd.testing.assert_frame_equal(frames["file"], frames["spec"], check_exact=True)
    common = [column for column in frames["builder"].columns if column in frames["spec"].columns]
    assert len(common) == len(frames["builder"].columns)
    pd.testing.assert_frame_equal(frames["builder"], frames["spec"][common], check_exact=True)


CLASS_BASED_ROOT = {
    "thermal_power": 3314218.4332571737,
    "electricity": 206436.37109026566,
    "cop": 16.054430795085086,
    "heat_loss": 1727799.1814901084,
}
"""The root outputs of simulate tick 3, written by the handwritten ``DoubletHeatPlant`` class."""


@pytest.mark.parametrize("way", ["builder", "spec", "file"])
def test_root_outputs_equal_the_handwritten_class_to_the_last_bit(runs, way):
    """Call order decides the bits of the sums: they equal the class-based plant's exactly."""
    outputs = runs[BACKENDS[0]][way][1].steps[3]["trees"][""]["outputs"]
    expected = (
        CLASS_BASED_ROOT
        if way != "builder"
        else {name: CLASS_BASED_ROOT[name] for name in ("electricity", "heat_loss")}
    )
    assert outputs == expected
