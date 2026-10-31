"""The plant file sections that every module tree shares."""

import json

import pytest

import gemini as gm
from gemini.errors import ValidationError
from gemini.modules._utils import serialization
from tests.fixtures.errors import raises


def test_a_handwritten_root_writes_its_class_and_flat_params():
    """Leaf and composite roots use the same format 2 file."""
    exchanger = gm.modules.HeatExchanger().update_params(hot_nominal_pressure_drop="2 bar")
    spec = exchanger.to_dict()
    assert spec["type"] == "HeatExchanger" and spec["format"] == 2
    assert spec["params"]["hot_nominal_pressure_drop"] == 2e5
    assert json.dumps(spec, allow_nan=False)
    assert gm.modules.HeatExchanger.from_dict(spec).to_dict() == spec


def test_fluids_bindings_and_history_round_trip():
    """Non-default sections are written and read back."""
    exchanger = gm.modules.HeatExchanger().update_params(thermal_conductance=1.0)
    exchanger.fluid = gm.WATER
    exchanger.set_bindings("", {"duty": {"column": "d", "unit": "kW"}})
    exchanger.set_params("", {"thermal_conductance": 2.0}, valid_from="2020-01-01")
    spec = exchanger.to_dict()
    assert spec["fluids"][""]["kind"] == "water" and "boundary" not in spec
    loaded = gm.modules.HeatExchanger.from_dict(spec)
    assert loaded.fluid == gm.WATER and loaded.to_dict() == spec


def test_old_files_are_refused_with_the_migration_named():
    """Format 1 raises ``old_format`` and names ``gm.plants.migrate``."""
    with raises(ValidationError, "old_format") as caught:
        gm.modules.HeatExchanger.from_dict({"version": 1, "modules": {}})
    assert caught.value.code == "old_format"
    assert "gm.plants.migrate" in str(caught.value)
    assert serialization.format_error({"format": 3}).code == "invalid_format"


def test_a_strict_report_raises_and_a_collecting_one_keeps_going():
    """``guard`` turns errors into problems with the path of the spec."""
    report = serialization.Report()
    with report.guard("a.b"):
        raise ValidationError("bad", path="c", suggestions=["x"])
    assert report.items == [
        {"path": "a.b.c", "message": "bad", "code": "invalid_value", "suggestions": ["x"]}
    ]
    with pytest.raises(ValidationError), serialization.Report(strict=True).guard("a"):
        raise ValidationError("bad")


def test_skips_matches_a_broken_module_and_its_children():
    """A module that failed to build hides the problems that only follow from it."""
    report = serialization.Report()
    report.broken.add("a")
    assert report.skips("a") and report.skips("a.b") and not report.skips("ab")


def test_keep_stated_keeps_equal_values_only():
    """A stated value stays while it still parses to the current one."""
    assert serialization.keep_stated("5", 5, int) == "5"
    assert serialization.keep_stated("5", 6, int) is None
    assert serialization.keep_stated("x", 6, int) is None
