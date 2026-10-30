"""One call of one module from plain JSON: shapes, units and errors."""

import json

import pytest

import gemini as gm
from tests.fixtures.errors import raises

ESP_PARAMETERS = {
    "stage_count": 12,
    "head_coefficients": [1.2e-10, -2.5e-6, 4e-3, 0.2, 5.0, 100.0],
    "power_coefficients": [1.0e-10, -1.0e-6, 3.0e-3, 0.3, 4.0, 200.0],
}
SUCTION = {"suction": {"flow": "150 m3/h", "T": "80 degC", "p": "20 bar"}}


def call(**changes):
    """Evaluate the ESP with the default JSON arguments, changed by keywords."""
    arguments = dict(
        module="ESP", parameters=ESP_PARAMETERS, inlets=SUCTION, controls={"frequency": "50 Hz"}
    )
    return gm.evaluate(**(arguments | changes))


def test_evaluate_returns_outlets_and_outputs_with_units():
    """Outlet streams and outputs are ``{value, unit}`` in SI and the result is plain JSON."""
    result = call()
    assert result["errors"] == []
    discharge = result["outlets"]["discharge"]
    assert set(discharge) == {"m_dot", "T", "p"}
    assert discharge["m_dot"]["unit"] == "kg/s" and discharge["T"]["unit"] == "K"
    assert discharge["p"]["unit"] == "Pa" and discharge["p"]["value"] > 20e5
    assert result["outputs"]["head"]["unit"] == "Pa"
    json.dumps(result, allow_nan=False)


def test_evaluate_equals_a_direct_call_bit_for_bit():
    """The JSON call is the same call: a class, a name and a built module agree."""
    from gemini.modules.pumps import ESP

    direct = ESP().update_params(**ESP_PARAMETERS)(
        gm.Stream(flow="150 m3/h", T="80 degC", p="20 bar"), frequency="50 Hz"
    )
    for module in ("ESP", ESP):
        result = call(module=module)
        assert result["outlets"]["discharge"]["p"]["value"] == direct.outlets.discharge.p
        assert result["outputs"]["head"]["value"] == direct.outputs.head


def test_evaluate_accepts_si_numbers_as_well_as_unit_strings():
    """Plain numbers are SI."""
    inlets = {"suction": {"m_dot": 12.0, "T": 353.15, "p": 2e6}}
    assert call(inlets=inlets)["errors"] == []


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"module": "ESp"}, "unknown_name"),
        ({"module": 3}, "invalid_value"),
        ({"parameters": {}}, "missing_value"),
        ({"parameters": {"stage_count": "many"}}, "invalid_value"),
        ({"inlets": {}}, "invalid_call"),
        ({"controls": {"frequency": "50 bar"}}, "invalid_unit"),
        ({"inlets": {"suction": {"flow": "1 m3/h", "T": "-5 K", "p": "1 bar"}}}, "invalid_call"),
    ],
)
def test_a_recorded_failure_returns_errors_instead_of_raising(changes, code):
    """Every failure is one ``GeminiError.to_dict()`` and the other parts are empty."""
    result = call(on_error="record", **changes)
    assert result["outlets"] == {} and result["outputs"] == {}
    assert [error["code"] for error in result["errors"]] == [code]
    assert set(result["errors"][0]) == {"path", "code", "message", "suggestions"}


def test_a_failing_call_raises_by_default():
    """``gm.evaluate`` has no never-raises rule: the same error reaches the caller."""
    with raises(gm.errors.ValidationError, "unknown_name") as caught:
        call(module="ESp")
    assert caught.value.suggestions == ("ESP",)
    with pytest.raises(gm.errors.ValidationError, match="on_error"):
        call(on_error="ignore")


def test_an_unknown_name_comes_with_suggestions():
    """The registry's close matches reach the error."""
    assert call(module="ESp", on_error="record")["errors"][0]["suggestions"] == ["ESP"]
