"""Discrete PID controller: start-of-step command, integral, derivative and anti-windup."""

import pytest

import gemini as gm
from gemini.core.modules import Module
from gemini.core.modules.control import PIDController
from gemini.core.modules.storage import ThermalStorage
from gemini.core.types import Boundary, Control, Inlet, Outlet, Output, Stream, Temperature


def _controller(**changes):
    """Return a reverse-acting PID controller with K = 2, Ti = 100 s and a 0..1 command."""
    params = dict(
        proportional_gain=2.0,
        integral_time=100.0,
        output_min=0.0,
        output_max=1.0,
        direction="reverse",
    )
    return PIDController().update_params(**(params | changes))


def _step(pid, state, dt, measurement):
    """Step the controller (which has no inlets) at a persisted measurement."""
    pid.measurement = measurement
    return pid.step(state, dt, {})


def test_plain_call_is_proportional_and_clamped():
    """Outside a step the initial states give K e, clamped to the output limits."""
    pid = _controller()
    out = pid(setpoint=1.0, measurement=0.8).outputs
    assert out.error == pytest.approx(0.2) and out.command == pytest.approx(0.4)
    assert not out.is_saturated
    out = pid(setpoint=1.0, measurement=0.0).outputs
    assert out.command == 1.0 and out.is_saturated
    direct = _controller(direction="direct")
    out = direct(setpoint=1.0, measurement=1.2).outputs
    assert out.error == pytest.approx(0.2) and out.command == pytest.approx(0.4)
    assert direct(setpoint=1.0, measurement=0.9).outputs.command == 0


def test_steps_integrate_and_differentiate_with_start_of_step_states():
    """I lags one step (explicit sum) and D is the backward difference over the last step."""
    pid = _controller(derivative_time=20.0)
    pid.setpoint = 1.0
    state, result = _step(pid, None, 10, 0.9)
    assert result.outputs.command == pytest.approx(2 * 0.1)
    assert state == {
        "integral": pytest.approx(2 * 10 / 100 * 0.1),
        "previous_error": pytest.approx(0.1),
        "previous_step": 10,
    }
    state, result = _step(pid, state, 10, 0.85)
    integral = 2 * 10 / 100 * 0.1
    derivative = 2 * 20 * (0.15 - 0.1) / 10
    assert result.outputs.command == pytest.approx(2 * 0.15 + integral + derivative)
    assert state["integral"] == pytest.approx(integral + 2 * 10 / 100 * 0.15)


def test_clamping_stops_windup_and_allows_unwinding():
    """A saturated command does not integrate further out, but integrates back in."""
    pid = _controller()
    pid.setpoint = 1.0
    state = {"integral": 0.9, "previous_error": None, "previous_step": None}
    held, result = _step(pid, state, 60, 0.5)
    assert result.outputs.is_saturated and held["integral"] == 0.9
    unwound, result = _step(pid, held, 60, 1.1)
    assert result.outputs.command == pytest.approx(0.9 - 0.2)
    assert unwound["integral"] == pytest.approx(0.9 - 2 * 60 / 100 * 0.1)
    proportional = _controller(integral_time=None)
    proportional.setpoint = 1.0
    assert _step(proportional, None, 60, 0.9)[0]["integral"] == 0


def test_invalid_settings_raise():
    """Crossed output limits and nonpositive tuning are configuration errors."""
    with pytest.raises(gm.errors.ConfigurationError, match="expected output_min < output_max"):
        _controller(output_min=1.0, output_max=0.0)(setpoint=1, measurement=0)
    with pytest.raises(gm.errors.DeclarationError):
        _controller(proportional_gain=0)
    with pytest.raises(gm.errors.DeclarationError):
        _controller(integral_time=0)
    with pytest.raises(gm.errors.MissingValueError):
        _controller()(setpoint=1)


class ControlledTank(Module):
    """Storage tank whose charge flow a PID controller throttles on a measured temperature."""

    def __init__(self):
        """Declare the test composite."""
        super().__init__()

        # Modules
        self.controller = _controller(proportional_gain=0.1, integral_time=600.0)
        self.storage = ThermalStorage().update_params(
            service="hot", volume=1.0, heat_loss_coefficient=0, reference_temperature=313.15
        )

        # Inlets
        self.charge_in = Inlet(Stream)
        self.discharge_in = Inlet(Stream)

        # Controls
        self.temperature_setpoint = Control(Temperature)

        # Boundaries
        self.measured_temperature = Boundary(Temperature)

        # Outputs
        self.command = Output.of(self.controller.command)

        # Outlets
        self.charge_out = Outlet(Stream)
        self.discharge_out = Outlet(Stream)

    def forward(self, inlets):
        """Throttle the charge flow by the controller command, then pass the tank."""

        # Modules
        control = self.controller(
            measurement=self.measured_temperature, setpoint=self.temperature_setpoint
        )
        charge_in = inlets.charge_in
        throttled = charge_in.with_(m_dot=charge_in.m_dot * control.outputs.command)
        stored = self.storage(
            charge_in=throttled, discharge_in=inlets.discharge_in, ambient_temperature=293.15
        )

        # Outlets
        charge_out = stored.outlets.charge_out
        discharge_out = stored.outlets.discharge_out

        outlets = dict(charge_out=charge_out, discharge_out=discharge_out)
        return outlets


def test_controller_steps_inside_a_composite():
    """The parent passes measurement= and uses the command; both children advance per step."""
    plant = ControlledTank().set_inputs(
        {"temperature_setpoint": 343.15, "measured_temperature": 333.15}
    )
    streams = {
        "charge_in": Stream(m_dot=1.0, T=353.15, p=3e5),
        "discharge_in": Stream(m_dot=0.0, T=313.15, p=3e5),
    }
    state, result = plant.step(None, 60, streams)
    assert result.outputs.command == pytest.approx(0.1 * 10)
    assert result.children["storage"].inlets.charge_in.m_dot == pytest.approx(1.0)
    assert state["controller"]["integral"] == 0
    plant.measured_temperature = 338.15
    state, result = plant.step(state, 60, streams)
    assert result.outputs.command == pytest.approx(0.1 * 5)
    assert state["controller"]["integral"] == pytest.approx(0.1 * 60 / 600 * 5)
    assert state["storage"]["temperature"] > 293.15
