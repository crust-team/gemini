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


def test_automatic_sums_cover_the_energy_outputs_leaves_declare(plant):
    """Without an ``outputs`` key the plant sums each energy output some leaf declares."""
    assert list(plant.outputs(recurse=False)) == ["heat_absorbed", "heat_loss"]


def test_each_kind_declares_one_output(plant):
    """``of``, ``sum`` and ``ratio`` declare outputs; ratios come after their operands."""
    plant._output_specs = {}
    plant._refresh()
    specs = {
        "ratio": {"ratio": ["duty", "heat_loss"]},
        "duty": {"of": "exchanger.duty"},
        "heat_loss": {"sum": "heat_loss"},
        "flow": {"of": "exchanger.cold_out", "field": "m_dot"},
    }
    ordered = [name for name, _ in outputs.ordered(specs)]
    assert ordered == ["duty", "heat_loss", "ratio", "flow"]
    for name, spec in outputs.ordered(specs):
        outputs.declare_output(plant, name, spec)
    assert list(plant.outputs(recurse=False)) == ordered


def test_bad_outputs_name_the_problem(plant):
    """Missing keys, unknown modules and outputs, non-additive sums and clashes are refused."""
    with pytest.raises(ValidationError):
        outputs.declare_output(plant, "x", {"of": "exchanger.duty", "sum": "heat_loss"})
    with raises(ValidationError, "unknown_name"):
        outputs.declare_output(plant, "x", {"of": "exchangr.duty"})
    with raises(ValidationError, "unknown_name") as caught:
        outputs.declare_output(plant, "x", {"of": "exchanger.dutty"})
    assert caught.value.suggestions == ("duty",)
    with raises(ValidationError, "unknown_name"):
        outputs.declare_output(plant, "x", {"sum": "nothing"})
    with pytest.raises(ValidationError):
        outputs.declare_output(plant, "x", {"sum": "effectiveness"})
    with pytest.raises(ValidationError):
        outputs.declare_output(plant, "pipe", {"sum": "heat_loss"})
