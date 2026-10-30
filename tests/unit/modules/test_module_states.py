"""Declared states: initial values, leaf and composite steps, and their validation."""

import pandas as pd
import pytest

import gemini as gm
from gemini.modules import Module
from gemini.types import (
    Control,
    Duty,
    Energy,
    Inlet,
    Outlet,
    Output,
    Parameter,
    State,
    Stream,
    Temperature,
)
from gemini.types.bindings import Binding, ModuleBindings
from tests.fixtures.errors import raises

STREAM = Stream(m_dot=1, T=350, p=1e6)


class Tank(Module):
    """Mixed tank whose temperature relaxes towards the inlet temperature."""

    def __init__(self):
        """Declare the test module."""
        super().__init__()

        # Parameters
        self.heat_capacity = Parameter(float, default=4217.4 * 100, gt=0)

        # Inlets
        self.inlet = Inlet(Stream)

        # States
        self.temperature = State(Temperature, default=300)

        # Outputs
        self.duty = Output(Duty)

        # Outlets
        self.outlet = Outlet(Stream)

    def forward(self, inlets):
        """Leave at the tank temperature of the start of the step."""

        # Outlets
        outlet = inlets.inlet.with_(T=self.temperature)

        outlets = dict(outlet=outlet)
        return outlets

    def _compute_outputs(self, inlets, outlets):
        self.duty = self._duty(inlets.inlet)

    def _advance_states(self, inlets, outlets, dt):
        return {
            "temperature": self.temperature + self._duty(inlets.inlet) * dt / self.heat_capacity
        }

    def _duty(self, inlet):
        return inlet.m_dot * 4217.4 * (inlet.T - self.temperature)


class Line(Module):
    """Two tanks in series."""

    def __init__(self):
        """Declare the test module."""
        super().__init__()

        # Modules
        self.first = Tank()
        self.second = Tank()

        # Inlets
        self.inlet = Inlet(Stream)

        # Outputs
        self.duty = Output(Duty)

        # Outlets
        self.outlet = Outlet(Stream)

    def forward(self, inlets):
        """Pass the stream through both tanks."""

        # Modules
        first = self.first(inlet=inlets.inlet)
        second = self.second(inlet=first.outlets.outlet)

        # Outlets
        outlet = second.outlets.outlet

        outlets = dict(outlet=outlet)
        return outlets


class Integrator(Module):
    """Accumulate a commanded rate over time."""

    def __init__(self):
        """Declare the test module."""
        super().__init__()

        # Controls
        self.rate = Control(float)

        # States
        self.total = State(Energy, default=0)

        # Outputs
        self.value = Output(Energy)

    def forward(self, inlets):
        """Move no fluid."""
        outlets = dict()
        return outlets

    def _compute_outputs(self, inlets, outlets):
        self.value = self.total

    def _advance_states(self, inlets, outlets, dt):
        return {"total": self.total + self.rate * dt}


def test_plain_call_uses_the_initial_state():
    """Outside a step a stateful module evaluates at its initial state."""
    tank = Tank()
    assert tank.stateful and not Line().stateful
    assert tank(inlet=STREAM).outlets.outlet.T == 300
    assert tank.initial_state() == {"temperature": 300}
    assert list(Line().states()) == ["first.temperature", "second.temperature"]
    assert "States:\n  temperature: K" in Tank.help()


def test_leaf_step_advances_its_state():
    """A leaf step starts from the given state and returns the end-of-step state."""
    tank = Tank()
    state, result = tank.step(None, 10, {"inlet": STREAM})
    assert result.outlets.outlet.T == 300
    assert state == {"temperature": pytest.approx(300 + 50 * 4217.4 * 10 / (4217.4 * 100))}
    state, result = tank.step(state, 10, {"inlet": STREAM})
    assert result.outlets.outlet.T == pytest.approx(305)


def test_composite_step_advances_every_descendant():
    """A composite steps its stateful children through its own forward, without a step method."""
    line = Line()
    assert line.initial_state() == {"first": {"temperature": 300}, "second": {"temperature": 300}}
    state, _ = line.step(None, 10, {"inlet": STREAM})
    state, result = line.step(state, 10, {"inlet": STREAM})
    assert state["first"]["temperature"] > state["second"]["temperature"] > 300
    assert result.outlets.outlet.T == 300
    first, second = 350 - 305, 305 - 300
    assert result.outputs.duty == pytest.approx(STREAM.m_dot * 4217.4 * (first + second))


def test_state_errors():
    """Unknown states, assignments, wrong returns and double calls fail with the module path."""
    tank = Tank()
    with raises(
        gm.errors.ValidationError, "unknown_name", match="tank: unknown state 'temperatur'"
    ):
        tank.step({"temperatur": 300}, 10, {"inlet": STREAM})
    with pytest.raises(gm.errors.DefinitionError, match="changes only in _advance_states"):
        tank.temperature = 310
    with pytest.raises(gm.errors.ValidationError, match="tank.temperature: invalid state"):
        tank.step({"temperature": -1}, 10, {"inlet": STREAM})
    line = Line()
    line.second = line.first
    with raises(gm.errors.ValidationError, "invalid_design", match="more than once in one step"):
        line.step(None, 10, {"inlet": STREAM})


def test_advance_states_must_return_every_state():
    """An incomplete end-of-step mapping is a configuration error."""

    class Leaky(Tank):
        """Tank that forgets its state."""

        def _advance_states(self, inlets, outlets, dt):
            return {}

    with raises(gm.errors.ValidationError, "invalid_design", match="expected temperature"):
        Leaky().step(None, 10, {"inlet": STREAM})


def test_engine_replay_integrates_declared_states():
    """The engine steps a declared-state twin and keeps its state between ticks."""
    plant = Integrator()
    plant.bindings = {"": ModuleBindings(controls={"rate": Binding(column="rate", unit="-")})}
    frame = pd.DataFrame(
        {"rate": [1.0, 1.0, 1.0]},
        index=pd.date_range("2024-01-01", periods=3, freq="1s", tz="UTC"),
    )
    engine = gm.Engine(plant, on_error="raise")
    assert engine.replay(gm.Dataset.from_frame(frame))[""].value.tolist() == [0, 1, 2]
    assert engine.module_states[""] == {"total": 3}
