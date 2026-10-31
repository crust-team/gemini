"""Outputs of a built plant from the spec."""

import pytest

import gemini as gm
from gemini.errors import ValidationError
from gemini.modules.plants import outputs
from tests.fixtures.errors import raises


@pytest.fixture
def plant():
    """Return a plant with a heat exchanger and a pipe."""
    result = gm.Plant("Outputs")
    result.add("HeatExchanger", "exchanger")
    result.add("Pipe", "pipe")
    return result


def test_a_plant_declares_no_total_of_its_own(plant):
    """Without an ``outputs`` key the plant declares nothing: totals are read from ports."""
    assert list(plant.outputs(recurse=False)) == []


def test_each_kind_declares_one_output(plant):
    """``of`` and ``ratio`` declare outputs; ratios come after their operands."""
    plant._output_specs = {}
    plant._refresh()
    specs = {
        "ratio": {"ratio": ["duty", "drop"]},
        "duty": {"of": "exchanger.duty"},
        "drop": {"of": "pipe.pressure_drop"},
        "flow": {"of": "exchanger.cold_out", "field": "m_dot"},
    }
    ordered = [name for name, _ in outputs.ordered(specs)]
    assert ordered == ["duty", "drop", "ratio", "flow"]
    for name, spec in outputs.ordered(specs):
        outputs.declare_output(plant, name, spec)
    assert list(plant.outputs(recurse=False)) == ordered


def test_bad_outputs_name_the_problem(plant):
    """Two keys, unknown modules and outputs, the removed ``sum`` and clashes are refused."""
    with pytest.raises(ValidationError):
        outputs.declare_output(plant, "x", {"of": "exchanger.duty", "ratio": ["a", "b"]})
    with raises(ValidationError, "unknown_name"):
        outputs.declare_output(plant, "x", {"of": "exchangr.duty"})
    with raises(ValidationError, "unknown_name") as caught:
        outputs.declare_output(plant, "x", {"of": "exchanger.dutty"})
    assert caught.value.suggestions == ("duty",)
    with raises(ValidationError, "invalid_format"):
        outputs.declare_output(plant, "x", {"sum": "heat_loss"})
    with pytest.raises(ValidationError):
        outputs.declare_output(plant, "pipe", {"of": "pipe.pressure_drop"})
