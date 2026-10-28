"""Contract tests independent of equipment calculations."""

import json

import pytest
from pydantic import BaseModel, Field, ValidationError

from gemini.core.base.component import Component, Health
from gemini.core.base.stream import Stream


class PassThrough(Component):
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

    def compute(self, inputs, streams_in):
        """Return the scalar product and unchanged stream."""
        return self.Outputs(value=self.params.value * inputs.multiplier), {
            "outlet": streams_in["inlet"]
        }


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
        c.compute({}, {})
    with pytest.raises(ValueError, match="extra"):
        c.compute({}, {"inlet": s, "other": s})
    with pytest.raises(ValidationError):
        c.compute({"multiplier": 0}, {"inlet": s})
    with pytest.raises(ValidationError):
        c.update_params(value=-1)
    assert c.params.value == 2
    state, out, streams = c.step("state", {}, {"inlet": s}, 1)
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

        def compute(self, inputs, streams_in):
            """Return an invalid output to exercise the base guard."""
            return {}, {}

    with pytest.raises(TypeError, match="compute must return"):
        WrongOutput({"value": 1}).compute({}, {"inlet": Stream(m_dot=1, T=300, p=1)})
    a = Health(score=1, alarm=False, message="ok")
    b = Health(score=1, alarm=False, message="ok")
    a.metrics["x"] = 1
    assert b.metrics == {}
