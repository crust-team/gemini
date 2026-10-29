"""Recorded call values, unit conversion on access and module result trees."""

import pytest

from gemini.core.types import Ports, Stream
from gemini.core.types.declarations import Output
from gemini.core.types.quantities import Power, PressureDifference, TemperatureDifference
from gemini.core.types.results import Health, ModuleResult, Values
from gemini.errors import UnitError


@pytest.fixture
def values():
    """Return values with declared power and difference quantities."""
    declarations = {
        "power": Output(Power),
        "head": Output(PressureDifference),
        "rise": Output(TemperatureDifference),
        "label": Output(str),
    }
    return Values({"power": 2000.0, "head": 1e5, "rise": 10.0, "label": "x"}, declarations)


def test_values_mapping_and_unit_conversion(values):
    """Values convert on request; differences convert by scale only."""
    assert values.power == values["power"] == 2000.0
    assert values.get("power", unit="kW") == 2
    assert values.get("head", unit="barg") == 1
    assert values.get("rise", unit="degC") == 10
    assert values.get("missing", 5) == 5
    with pytest.raises(UnitError, match="label"):
        values.get("label", unit="m")


def test_unknown_values_suggest_close_names(values):
    """Misspelled names list the valid names and the closest one."""
    with pytest.raises(AttributeError, match="'powr'.*valid names: power.*did you mean 'power'"):
        values.powr
    with pytest.raises(KeyError, match="'hed'"):
        values["hed"]


def test_module_result_leaves():
    """Leaves flatten descendant results with relative paths."""
    stream = Stream(m_dot=1, T=300, p=1e5)
    leaf = ModuleResult(outputs=Values(), outlets=Ports({"outlet": stream}))
    parent = ModuleResult(
        outputs=Values(), outlets=Ports(), children={"a": leaf, "b": leaf}, is_leaf=False
    )
    root = ModuleResult(outputs=Values(), outlets=Ports(), children={"p": parent}, is_leaf=False)
    assert root.leaves() == {"p.a": leaf, "p.b": leaf}
    assert leaf.leaves("x") == {"x": leaf}


def test_health_bounds():
    """The condition score is a fraction."""
    assert Health(score=1, alarm=False, message="ok").assessed
    with pytest.raises(ValueError):
        Health(score=1.5, alarm=False, message="bad")
