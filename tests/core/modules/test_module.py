"""Contract tests independent of equipment calculations."""

import json

import pytest
from pydantic import BaseModel, Field, ValidationError

from gemini.core.base.health import Health
from gemini.core.base.stream import Stream
from gemini.core.modules.module import Module, ModuleResult


class PassThrough(Module):
    """Contract fixture passing an inlet stream through unchanged."""

    name = "test_passthrough"
    category = "test"
    description = "Contract fixture."
    inlets = ("inlet",)
    outlets = ("outlet",)

    class Params(BaseModel):
        """Positive test parameter."""

        value: float = Field(..., gt=0, description="Fixture value [-]")

    class Inputs(BaseModel):
        """Validated operating input."""

        multiplier: float = Field(1, gt=0, description="Multiplier [-]")

    class Outputs(BaseModel):
        """Predicted scalar."""

        value: float = Field(..., description="Fixture result [-]")

    def forward(self, inputs, streams_in):
        """Return the scalar product and unchanged stream."""
        return ModuleResult(
            self.Outputs(value=self.params.value * inputs.multiplier),
            {"outlet": streams_in["inlet"]},
        )


def test_stream_validation_and_copy():
    """Streams reject nonphysical updates and preserve originals."""
    s = Stream(m_dot=10, T=300, p=100000)
    assert s.volumetric_flow() == 0.01
    assert s.with_(p=200000).p == 200000
    assert s.p == 100000
    with pytest.raises(ValidationError):
        s.with_(p=-1)
    with pytest.raises(ValidationError):
        s.T = 0


def test_contract_and_state():
    """Direct compute calls enforce ports, inputs and stateless stepping."""
    c = PassThrough({"value": 2})
    s = Stream(m_dot=1, T=300, p=100000)
    with pytest.raises(ValueError, match="test_passthrough.*missing.*inlet"):
        c({}, {})
    with pytest.raises(ValueError, match="extra"):
        c({}, {"inlet": s, "other": s})
    with pytest.raises(ValidationError):
        c({"multiplier": 0}, {"inlet": s})
    with pytest.raises(ValidationError):
        c.update_params(value=-1)
    assert c.params.value == 2
    state, (out, streams) = c.step("state", {}, {"inlet": s}, 1)
    assert state == "state" and out.value == 2 and streams["outlet"] == s
    assert c.initial_state() is None and c.capex() is None and c.health(out, {}) is None
    json.dumps(c.schema())


def test_invalid_declaration_and_return():
    """Invalid sensor names and output contracts fail with clear errors."""
    with pytest.raises(TypeError, match="unknown schema"):

        class Invalid(PassThrough):
            """Malformed metadata fixture."""

            soft_sensors = ("absent",)

    class WrongOutput(PassThrough):
        """Malformed return fixture."""

        def forward(self, inputs, streams_in):
            """Return an invalid output to exercise the base guard."""
            return ModuleResult({}, {})

    with pytest.raises(TypeError, match="forward must return"):
        WrongOutput({"value": 1})({}, {"inlet": Stream(m_dot=1, T=300, p=1)})
    a = Health(score=1, alarm=False, message="ok")
    b = Health(score=1, alarm=False, message="ok")
    a.metrics["x"] = 1
    assert b.metrics == {}


def test_recursive_parameters_state_and_hooks():
    """Nested trees preserve validated state and hook order across JSON round trips."""
    from gemini.core.modules.module import Sequential

    class FitPass(PassThrough):
        """Calibratable fixture."""

        calibratable = ("value",)

    first, second = FitPass({"value": 2}), FitPass({"value": 3})
    plant = Sequential({"first": first, "second": second})
    plant._set_path("plant")
    assert list(plant.named_modules()) == [("", plant), ("first", first), ("second", second)]
    assert plant.get_submodule("first") is first
    assert dict(plant.named_params()) == {"first.value": 2, "second.value": 3}
    ref = plant.calibratable_params()[0]
    assert ref.path == "first.value" and ref.bounds == (0, float("inf"))
    with pytest.raises(ValidationError):
        plant.set_param("first.value", -2)
    assert plant.get_param("first.value") == 2
    state = json.loads(json.dumps(plant.state_dict()))
    plant.set_param("first.value", 7)
    plant.load_state_dict(state)
    assert first.params.value == 2
    with pytest.raises(ValueError, match="state paths"):
        plant.load_state_dict({"first": state["first"]})
    plant.load_state_dict({"first": state["first"], "unknown": {}}, strict=False)
    bad = json.loads(json.dumps(state))
    bad["second"]["params"]["value"] = -1
    bad["first"]["params"]["value"] = 10
    with pytest.raises(ValidationError):
        plant.load_state_dict(bad)
    assert first.params.value == 2
    calls = []
    a = first.register_forward_pre_hook(lambda *args: calls.append("pre"))
    b = first.register_forward_hook(lambda *args: calls.append("post"))
    stream = Stream(m_dot=1, T=300, p=1e5)
    result = plant({"first": {"multiplier": 4}}, inlet=stream)
    assert result.outputs.root["first"].value == 8
    assert result.streams["outlet"] == stream
    assert calls == ["pre", "post"]
    a.remove()
    a.remove()
    b.remove()
    plant(inlet=stream)
    assert calls == ["pre", "post"]
    with pytest.raises(ValueError, match="plant.first.*missing"):
        first()
    with pytest.raises(ValueError, match="cycle"):
        first.add_module("parent", plant)
    visited = []
    assert plant.apply(visited.append) is plant
    assert visited == [second, first, plant]
    del plant.second
    assert list(plant.children()) == [first]
