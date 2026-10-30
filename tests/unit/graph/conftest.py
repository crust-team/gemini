"""A small traceable leaf module shared by the graph tests."""

import numpy as np
import pytest

from gemini import ops
from gemini.core.modules import Module
from gemini.core.types import Control, Inlet, Outlet, Output, Parameter, Stream
from gemini.errors import PhysicsRangeError
from gemini.ops import Constant

REFERENCE = Constant("REFERENCE", 2.0, "Pa", "pressure rise per unit gain and scale")


class Gain(Module):
    """Raise the inlet pressure by ``gain * scale * REFERENCE``; refuse a negative gain."""

    def __init__(self):
        """Declare one numeric and one text parameter, a control and two outputs."""
        super().__init__()

        # Parameters
        self.scale = Parameter(float)
        self.label = Parameter(str, default="x")

        # Inlets
        self.inlet = Inlet(Stream)

        # Controls
        self.gain = Control(float)

        # Outputs
        self.rise = Output(float)
        self.boost = Output(float)

        # Outlets
        self.outlet = Outlet(Stream)

    def forward(self, inlets):
        """Raise the pressure."""

        # Outlets
        inlet = inlets.inlet
        ops.check(
            self.gain >= 0,
            PhysicsRangeError,
            "{path}: gain = {gain}",
            path=self.path,
            gain=self.gain,
        )
        outlet = inlet.with_(p=inlet.p + self.gain * self.scale * REFERENCE)

        outlets = dict(outlet=outlet)
        return outlets

    def _compute_outputs(self, inlets, outlets):
        self.rise = outlets.outlet.p - inlets.inlet.p
        self.boost = ops.where(self.rise > 0, ops.truediv(self.rise, self.gain), 0.0)


@pytest.fixture
def gain():
    """Return a configured ``Gain`` module."""
    return Gain().update_params(scale=3.0)


@pytest.fixture
def inlet():
    """Return a three-row inlet state."""
    return Stream(
        m_dot=np.array([1.0, 1.0, 1.0]),
        T=np.array([300.0, 310.0, 320.0]),
        p=np.array([1e5, 2e5, 3e5]),
        fluid=Gain().fluid,
    )


class Stepper(Module):
    """Raise the inlet pressure ``steps`` times by one pascal; ``steps`` is structural."""

    def __init__(self):
        """Declare a structural count, a numeric increment, an inlet and an outlet."""
        super().__init__()

        # Parameters
        self.steps = Parameter(int, default=2, structural=True)
        self.increment = Parameter(float, default=1.0)

        # Inlets
        self.inlet = Inlet(Stream)

        # Outlets
        self.outlet = Outlet(Stream)

    def forward(self, inlets):
        """Add the increment once per step."""

        # Outlets
        pressure = inlets.inlet.p
        for _ in range(self.steps):
            pressure = pressure + self.increment
        return dict(outlet=inlets.inlet.with_(p=pressure))


@pytest.fixture
def stepper():
    """Return a configured ``Stepper`` module."""
    return Stepper()


class Source(Module):
    """Emit a stream of fixed state whose mass flow is the ``rate`` control; it has no inlet."""

    def __init__(self):
        """Declare a control, an output and an outlet."""
        super().__init__()

        # Controls
        self.rate = Control(float)

        # Outputs
        self.double = Output(float)

        # Outlets
        self.outlet = Outlet(Stream)

    def forward(self, inlets):
        """Emit the stream."""

        # Outlets
        outlet = Stream(m_dot=self.rate, T=300.0, p=1e5, fluid=self.fluid)
        return dict(outlet=outlet)

    def _compute_outputs(self, inlets, outlets):
        self.double = 2 * outlets.outlet.m_dot


@pytest.fixture
def source():
    """Return a ``Source`` module."""
    return Source()
