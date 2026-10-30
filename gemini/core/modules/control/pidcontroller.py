"""Discrete PID controller with output limits and clamping anti-windup."""

from typing import Literal

from gemini import ops
from gemini.core.modules.module import Module
from gemini.core.types import (
    Boundary,
    Control,
    Dimensionless,
    Duration,
    Output,
    Parameter,
    State,
)
from gemini.errors import ConfigurationError


class PIDController(Module):
    """Discrete PID controller with output limits and clamping anti-windup; no fluid ports.

    The error is ``e = setpoint - measurement`` for ``direction="reverse"`` (the command rises
    when the measurement falls, as for a heating valve) and ``e = measurement - setpoint`` for
    ``direction="direct"`` (as for a cooling valve). With the gain ``K``, the integral time
    ``Ti`` and the derivative time ``Td`` the command of step k is the ideal (ISA) form,
    discretised as in Astrom and Hagglund 2006, *Advanced PID Control*, chapter 3:

        u_k = clamp(K * e_k + I_k + D_k, output_min, output_max)
        D_k = K * Td * (e_k - e_(k-1)) / h_(k-1)
        I_(k+1) = I_k + K * h_k / Ti * e_k

    The states are ``integral`` I (in command units), ``previous_error`` e_(k-1) and
    ``previous_step`` h_(k-1) [s]. The step length h_k is known only when the states advance,
    so the command uses start-of-step states only: the integral is the explicit (forward
    rectangular) sum of the errors before this step, a one-step lag of the integral action, and
    the derivative is the backward difference of the last two errors over the previous step
    length, exact for a uniform clock. Before the first step (``previous_error`` is ``None``)
    the derivative is zero. The derivative acts on the error, so a setpoint change kicks it
    once; it is not filtered, so noisy measurements need ``derivative_time = 0`` (the
    default) or a filtered measurement.

    Anti-windup is clamping (conditional integration): the integral does not change over a step
    whose unclamped command already exceeds a limit while the error drives it further out.
    ``integral_time=None`` gives P or PD control. Outside ``step`` a call uses the initial
    states, so it returns the proportional command only.

    A parent composite calls the controller in ``forward`` with ``measurement=`` (and
    optionally ``setpoint=``) and uses ``result.outputs.command``; the controller is stateful, so
    call it once per step.

    NOTE(refactor): the integral, the previous error and the previous step are states, and
    ``previous_error`` being ``None`` before the first step is structural, so the module is a
    graph break until ``scan`` exists; its arithmetic is written with ops all the same.
    """

    category = "network"

    def __init__(self):
        """Declare the tuning, the limits, the controller memory and the command."""
        super().__init__()

        # Parameters
        self.proportional_gain = Parameter(Dimensionless, gt=0)
        self.integral_time = Parameter(Duration | None, default=None, gt=0)
        self.derivative_time = Parameter(Duration, default=0)
        self.output_min = Parameter(Dimensionless)
        self.output_max = Parameter(Dimensionless)
        self.direction = Parameter(Literal["direct", "reverse"])

        # Controls
        self.setpoint = Control(Dimensionless)

        # Boundaries
        self.measurement = Boundary(Dimensionless)

        # States
        self.integral = State(Dimensionless, default=0)
        self.previous_error = State(Dimensionless | None, default=None)
        self.previous_step = State(Duration | None, default=None, gt=0)

        # Outputs
        self.error = Output(Dimensionless)
        self.command = Output(Dimensionless)
        self.is_saturated = Output(bool)

    def forward(self, inlets):
        """Move no fluid; the command is an output."""
        outlets = dict()
        return outlets

    def _compute_outputs(self, inlets, outlets):
        unclamped = self._unclamped_command()
        self.error = self._error()
        self.command = ops.minimum(self.output_max, ops.maximum(self.output_min, unclamped))
        self.is_saturated = self.command != unclamped

    def _advance_states(self, inlets, outlets, dt):
        error = self._error()
        unclamped = self._unclamped_command()
        increment = 0.0
        if self.integral_time is not None:
            increment = self.proportional_gain * dt / self.integral_time * error
        winding_up = ops.logical_and(unclamped >= self.output_max, increment > 0)
        winding_down = ops.logical_and(unclamped <= self.output_min, increment < 0)
        increment = ops.where(ops.logical_or(winding_up, winding_down), 0.0, increment)
        return {"integral": self.integral + increment, "previous_error": error, "previous_step": dt}

    def _error(self):
        """Return the control error in the sense of ``direction``."""
        if self.direction == "reverse":
            return self.setpoint - self.measurement
        return self.measurement - self.setpoint

    def _unclamped_command(self):
        """Return K * e + I + D from the start-of-step states, before the output limits."""
        ops.check(
            self.output_min < self.output_max,
            ConfigurationError,
            "{path}: output_min = {output_min}, output_max = {output_max}; "
            "expected output_min < output_max",
            path=self.path,
            output_min=self.output_min,
            output_max=self.output_max,
        )
        error = self._error()
        derivative = 0.0
        if self.previous_error is not None and self.previous_step is not None:
            change = error - self.previous_error
            derivative = self.proportional_gain * self.derivative_time * change / self.previous_step
        return self.proportional_gain * error + self.integral + derivative
