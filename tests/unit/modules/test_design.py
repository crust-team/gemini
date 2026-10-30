"""Dated parameters and bindings of a module tree."""

import pytest

import gemini as gm
from gemini.errors import BindingError, UnitError, UnknownNameError
from gemini.modules import design

BINDING = {"column": "x", "unit": "kW/K"}


@pytest.fixture
def exchanger():
    """Return a heat exchanger with a design."""
    return gm.modules.HeatExchanger().set_params(
        "", {"ua": 1e3, "dp_hot_nominal": 1e4, "dp_cold_nominal": 1e4}
    )


def test_an_undated_set_changes_the_base_and_the_current_value(exchanger):
    """Unit strings are converted, and the value is in force at once."""
    exchanger.set_params("", {"dp_hot_nominal": "2 bar"})
    assert exchanger.dp_hot_nominal == 2e5
    assert exchanger.params_at("")["dp_hot_nominal"] == 2e5
    history = exchanger.param_history("")
    assert len(history) == 1 and history[0]["valid_from"] is None
    assert history[0]["params"]["dp_hot_nominal"] == 2e5


def test_a_dated_snapshot_is_complete_and_sorted(exchanger):
    """Each snapshot holds the values in force merged with the change."""
    exchanger.set_params("", {"ua": 5.0}, valid_from="2021-01-01")
    exchanger.set_params("", {"ua": 3.0}, valid_from="2020-01-01")
    history = exchanger.param_history("")
    assert [item["valid_from"] for item in history] == [
        None,
        "2020-01-01T00:00:00Z",
        "2021-01-01T00:00:00Z",
    ]
    assert history[2]["params"].keys() == history[0]["params"].keys()
    assert exchanger.params_at("", "2020-06-01")["ua"] == 3.0
    assert exchanger.params_at("")["ua"] == 5.0


def test_an_unknown_parameter_suggests_a_name(exchanger):
    """The error names the closest parameter."""
    with pytest.raises(UnknownNameError) as caught:
        exchanger.set_params("", {"uaa": 1.0})
    assert caught.value.suggestions == ("ua",)


def test_bindable_lists_what_a_module_accepts(exchanger):
    """Controls, boundaries, inlet fields, measured outputs and states by name."""
    bindable = exchanger.bindable("")
    assert bindable["inlets"]["hot_in"] == ["m_dot", "T", "p"]
    assert "duty" in bindable["measured"]
    assert set(bindable) == {"controls", "boundaries", "inlets", "measured", "state"}


def test_bindings_check_units_against_the_declaration(exchanger):
    """A column in a unit of another dimension is refused; a fitting one is stored."""
    with pytest.raises(UnitError):
        exchanger.set_bindings("", {"measured": {"duty": {"column": "d", "unit": "bar"}}})
    exchanger.set_bindings("", {"measured": {"duty": {"column": "d", "unit": "kW"}}})
    assert exchanger.bindings[""].measured["duty"].unit == "kW"
    exchanger.set_bindings("", {})
    assert exchanger.bindings == {}


def test_bindings_reject_unknown_names_and_fields(exchanger):
    """Names and inlet fields are checked."""
    with pytest.raises(UnknownNameError):
        exchanger.set_bindings("", {"measured": {"dutty": {"column": "d", "unit": "kW"}}})
    with pytest.raises(UnknownNameError):
        exchanger.set_bindings("", {"inlets": {"hot_in": {"q": {"column": "d", "unit": "K"}}}})
    with pytest.raises(BindingError):
        exchanger.set_bindings("", {"measured": {"duty": {"column": "d"}}})


def test_a_volume_flow_column_fits_a_mass_flow_inlet_field():
    """Inlet flow columns may be volumetric; the engine converts them."""
    assert design.FIELD_UNITS["m_dot"] == ("kg/s", "m3/s")
