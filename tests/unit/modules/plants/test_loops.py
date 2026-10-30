"""Loop closure: Wegstein fixed point and unrecorded trial calls."""

import pytest

import gemini as gm
from gemini.backends import runtime
from gemini.modules import Module
from gemini.modules.plants import loops
from gemini.modules.storage import ThermalStorage
from gemini.types import Inlet, Outlet, Output, Stream
from tests.fixtures.errors import raises

STREAM = Stream(m_dot=1.0, T=300.0, p=1e5)


class Heater(Module):
    """Add 1 K, or 2 K under float32 precision, to the inlet temperature."""

    def __init__(self):
        """Declare the test module."""
        super().__init__()

        # Inlets
        self.inlet = Inlet(Stream)

        # Outputs
        self.rise = Output(float)

        # Outlets
        self.outlet = Outlet(Stream)

    def forward(self, inlets):
        """Warm the stream by the precision-dependent rise."""

        # Outlets
        outlet = inlets.inlet.with_(T=inlets.inlet.T + _rise())

        outlets = dict(outlet=outlet)
        return outlets

    def _compute_outputs(self, inlets, outlets):
        self.rise = _rise()


def _rise():
    """Return the test rise [K] for the current runtime precision."""
    return 2.0 if runtime.get_precision() == "float32" else 1.0


class Twice(Module):
    """Evaluate the heater once detached, then once as a recorded child."""

    def __init__(self):
        """Declare the test composite."""
        super().__init__()

        # Modules
        self.heater = Heater()

        # Inlets
        self.inlet = Inlet(Stream)

        # Outputs
        self.rise = Output.of(self.heater.rise)

        # Outlets
        self.outlet = Outlet(Stream)

    def forward(self, inlets):
        """Use the detached trial as the recorded call's inlet."""

        # Modules
        trial = self.heater.trial_outlets({"inlet": inlets.inlet})
        heated = self.heater(inlet=trial.outlet)

        # Outlets
        outlet = heated.outlets.outlet

        outlets = dict(outlet=outlet)
        return outlets


def test_linear_loop_closes_in_three_passes():
    """Wegstein's step is exact on a linear map: substitution, secant step, confirmation."""
    calls = []

    def update(value):
        calls.append(value)
        return 0.9 * value + 3.0

    assert loops.close_loop(update, 0.0, "loop") == pytest.approx(30.0, abs=1e-9)
    assert len(calls) == 3


def test_clamped_loop_and_capped_map():
    """Iterates stay within the bounds; a map capped at a floor converges onto it."""

    def update(value):
        assert value <= 50.0
        return max(40.0, value - 5.0)

    assert loops.close_loop(update, 60.0, "loop", upper=50.0) == 40.0
    assert loops.close_loop(lambda value: value, 7.0, "loop") == 7.0


def test_diverging_loop_raises():
    """A map without a fixed point exhausts the passes and names the loop."""
    with pytest.raises(gm.errors.PhysicsError, match="plant: loop temperature"):
        loops.close_loop(lambda value: value + 1.0, 0.0, "plant")


def test_detached_call_is_not_recorded():
    """The trial call is invisible to the parent; the recorded call is the only child call."""
    plant = Twice()
    result = plant(inlet=STREAM)
    assert result.outlets.outlet.T == 302.0
    assert list(result.leaves()) == ["heater"]
    assert result.outputs.rise == 1.0


def test_detached_call_keeps_runtime_settings():
    """A trial call runs with the caller's runtime settings."""
    with gm.runtime.settings(precision="float32"):
        trial = Heater().trial_outlets({"inlet": STREAM})
    assert trial.outlet.T == 302.0


def test_detached_call_rejects_stateful_modules():
    """A stateful module would be evaluated at its initial states, so it is refused."""
    with raises(
        gm.errors.ValidationError, "invalid_design", match="stateless module for a trial call"
    ):
        ThermalStorage().trial_outlets({})
