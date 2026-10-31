"""Every public function that returns data gives plain JSON on the example plant."""

import json

import pytest

import gemini as gm


@pytest.fixture(scope="module")
def plant():
    """Give the example plant, not shared with tests that mutate it."""
    return gm.plants.example("DoubletHeatPlant")


@pytest.fixture(scope="module")
def results(plant, fast_dataset):
    """Give a replay of six hours of the short-window dataset."""
    window = fast_dataset.window(end=fast_dataset.start + gm.Clock.days(2024, 7, 1).step * 6)
    return gm.replay(plant, window)


CALLS = {
    "modules.names": lambda plant, results: gm.modules.names(),
    "modules.categories": lambda plant, results: gm.modules.categories(),
    "streams.names": lambda plant, results: gm.streams.names(),
    "units.names": lambda plant, results: gm.units.names("pressure"),
    "units.parse": lambda plant, results: gm.units.parse("150 m3/h"),
    "describe": lambda plant, results: plant.describe(),
    "class.describe": lambda plant, results: gm.modules.ESP.describe(),
    "parameter_schema": lambda plant, results: gm.modules.ESP.parameter_schema(),
    "validate_params": lambda plant, results: gm.modules.Valve.validate_params(
        {"nope": 1}, on_error="record"
    ),
    "plants.names": lambda plant, results: gm.plants.names(),
    "plants.validate": lambda plant, results: gm.plants.validate({"format": 2}, on_error="record"),
    "schema": lambda plant, results: gm.plants.schema(),
    "profile_schema": lambda plant, results: gm.profiles.profile_schema(),
    "to_spec": lambda plant, results: plant.to_dict(),
    "plant.validate": lambda plant, results: plant.validate(),
    "bindable": lambda plant, results: plant.bindable("heat_exchanger"),
    "params_at": lambda plant, results: plant.params_at("heat_exchanger"),
    "param_history": lambda plant, results: plant.param_history("heat_exchanger"),
    "results.names": lambda plant, results: results.names(),
    "results.get": lambda plant, results: results.get("heat_exchanger", "duty"),
    "results.summary": lambda plant, results: results.summary(),
    "results.errors": lambda plant, results: results.errors(),
    "results.to_dict": lambda plant, results: results.to_dict(),
    "results.end_state": lambda plant, results: results.end_state,
    "evaluate": lambda plant, results: gm.evaluate("Valve", {}, {}, {}, on_error="record"),
    "kpi": lambda plant, results: gm.kpi.compute(plant, results),
    "kpi.names": lambda plant, results: gm.kpi.names(),
    "checks.run_all": lambda plant, results: gm.checks.run_all(plant, results),
    "economics.capex": lambda plant, results: gm.economics.capex(plant, on_error="record"),
    "testing.check_module": lambda plant, results: gm.testing.check_module(gm.modules.Valve),
    "error.to_dict": lambda plant, results: gm.errors.ValidationError(
        "bad", code="invalid_unit"
    ).to_dict(),
}


@pytest.mark.parametrize("name", CALLS)
def test_returns_are_plain_json(name, plant, results):
    """``json.dumps`` without NaN accepts the return, whose types are JSON's own."""
    result = CALLS[name](plant, results)
    assert json.loads(json.dumps(result, allow_nan=False)) == json.loads(json.dumps(result))
