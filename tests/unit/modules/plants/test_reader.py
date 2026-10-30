"""Reading a spec: every problem at once, with the path into the spec."""

import copy

import pytest

import gemini as gm
from gemini.errors import ValidationError
from gemini.modules.plants import reader


@pytest.fixture
def spec():
    """Return a valid spec with a group, a nested plant, a named port and an output."""
    return {
        "format": 2,
        "name": "Test",
        "modules": {
            "degasser": {"type": "Degasser", "params": {}},
            "filters": {"type": "ModuleDict", "modules": {"hot": {"type": "Filter", "params": {}}}},
            "pipe": {"type": "Pipe", "params": {"length": "100 ft"}},
        },
        "connections": [{"source": "degasser.liquid", "target": "filters.hot.inlet"}],
        "outlets": {"product": "filters.hot.outlet"},
        "outputs": {"loss": {"sum": "heat_loss"}},
        "bindings": {},
        "param_history": {},
    }


def problems_of(spec, **changes):
    """Return the problems of a copy of ``spec`` with top-level ``changes``."""
    return gm.plants.validate(copy.deepcopy(spec) | changes)


def test_a_valid_spec_has_no_problems(spec):
    """The base spec builds."""
    assert gm.plants.validate(spec) == []


def test_every_problem_is_reported_at_once_with_its_path(spec):
    """Several mistakes give several problems, none raised."""
    spec["modules"]["degasser"]["type"] = "Degaser"
    spec["modules"]["pipe"]["params"] = {"length": "2 bar", "lenght": 1, "diameter": -1}
    codes = {item["path"]: item["code"] for item in gm.plants.validate(spec)}
    assert codes["modules.degasser.type"] == "unknown_name"
    assert codes["modules.pipe.params.length"] == "invalid_unit"
    assert codes["modules.pipe.params.lenght"] == "unknown_name"
    assert gm.plants.validate(spec)[0]["suggestions"][0] == "Degasser"


def test_an_out_of_bounds_value_has_its_own_code(spec):
    """A value below its minimum is ``out_of_bounds``."""
    spec["modules"]["pipe"]["params"] = {"length": -5.0}
    (item,) = gm.plants.validate(spec)
    assert item["code"] == "out_of_bounds" and item["path"] == "modules.pipe.params.length"


def test_wiring_rules_report_the_connection_and_the_field(spec):
    """Each wiring rule has its code and points at ``connections[i].source|target``."""
    spec["modules"]["pipe2"] = {"type": "Pipe", "params": {}}
    spec["modules"]["filter2"] = {"type": "Filter", "params": {}}
    cases = {
        "unknown_name": ("pipe.outlet", "filter.hot.inlet", "target"),
        "unknown_port": ("pipe.outlt", "pipe2.inlet", "source"),
        "port_in_use": ("pipe.outlet", "filters.hot.inlet", "target"),
        "stream_mismatch": ("degasser.gas", "filter2.inlet", "target"),
        "invalid_connection": ("pipe", "pipe2.inlet", "source"),
        "loop_without_state": ("pipe.outlet", "pipe.inlet", "target"),
    }
    for code, (source, target, field) in cases.items():
        extra = {"source": source, "target": target}
        found = problems_of(spec, connections=spec["connections"] + [extra])
        assert [(item["code"], item["path"]) for item in found] == [
            (code, f"connections[1].{field}")
        ], code


def test_ambiguous_ports_are_listed(spec):
    """A bare module name needs a port in a spec; an ambiguous pair is refused elsewhere."""
    spec["modules"]["splitter"] = {"type": "Splitter", "params": {}}
    spec["connections"].append({"source": "splitter", "target": "pipe.inlet"})
    (item,) = gm.plants.validate(spec)
    assert item["code"] == "invalid_connection"
    assert item["suggestions"] == ["splitter.first_out", "splitter.second_out"]


def test_a_failed_module_does_not_bury_the_report_in_follow_ups(spec):
    """Connections and sections naming a module that did not build are not reported again."""
    spec["modules"]["degasser"]["type"] = "Degaser"
    spec["fluids"] = {"degasser": {}}
    assert [item["path"] for item in gm.plants.validate(spec)] == ["modules.degasser.type"]


def test_shape_and_format_problems(spec):
    """Unknown keys, wrong types and old files are problems, not exceptions."""
    found = problems_of(spec, modul={}, modules=[])
    assert {"modul", "modules"} <= {item["path"] for item in found}
    assert gm.plants.validate({"version": 1})[0]["code"] == "old_format"
    assert gm.plants.validate([])[0]["code"] == "invalid_format"
    assert gm.plants.validate({"format": 2, "name": 3})[0]["path"] == "name"


def test_sections_are_checked_per_path(spec):
    """Fluids, boundary, bindings and history name the module path in the problem."""
    found = problems_of(
        spec,
        fluids={"nowhere": {}},
        boundary={"pipe": []},
        bindings={"pipe": {"measured": {"nothing": {"column": "c", "unit": "W"}}}},
        param_history={"pipe": [{"valid_from": "2020-01-01", "params": {"lenght": 1}}]},
    )
    assert {item["path"] for item in found} == {
        "fluids.nowhere",
        "boundary.pipe",
        "bindings.pipe.measured.nothing",
        "param_history.pipe",
    }


def test_read_raises_one_error_that_lists_every_problem(spec):
    """``from_spec`` raises a ``ValidationError`` with all messages and the first path."""
    spec["modules"]["degasser"]["type"] = "Degaser"
    spec["modules"]["pipe"]["params"] = {"lenght": 1}
    with pytest.raises(ValidationError) as caught:
        reader.read(gm.Plant, spec)
    assert caught.value.path == "modules.degasser.type"
    assert "modules.pipe.params.lenght" in str(caught.value)
