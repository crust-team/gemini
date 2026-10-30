"""A small traceable leaf module shared by the graph tests."""

import numpy as np
import pytest

from gemini import ops
from gemini.core.modules import Module
from gemini.core.types import (
    BRINE,
    WATER,
    Boundary,
    Control,
    Electricity,
    Inlet,
    Outlet,
    Output,
    Parameter,
    Pressure,
    Ratio,
    State,
    Stream,
    Temperature,
)
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


class Meter(Module):
    """Pass the stream on and draw ``draw * scale`` watts; a leaf with an additive output."""

    def __init__(self):
        """Declare a parameter, a control, an inlet, an additive output and an outlet."""
        super().__init__()

        # Parameters
        self.scale = Parameter(float, default=2.0)

        # Inlets
        self.inlet = Inlet(Stream)

        # Controls
        self.draw = Control(float, ge=0)

        # Outputs
        self.electricity = Output(Electricity)

        # Outlets
        self.outlet = Outlet(Stream)

    def forward(self, inlets):
        """Pass the stream."""

        # Outlets
        outlets = dict(outlet=inlets.inlet)
        return outlets

    def _compute_outputs(self, inlets, outlets):
        self.electricity = self.draw * self.scale


class Line(Module):
    """A meter, then a gain, then a second meter: a composite with every output formula."""

    def __init__(self):
        """Declare the children, the output formulas and the ports."""
        super().__init__()

        # Modules
        self.first = Meter()
        self.gain = Gain().update_params(scale=3.0)
        self.second = Meter()

        # Inlets
        self.inlet = Inlet(Stream)

        # Controls
        self.boost = Control(float, default=1.0)

        # Outputs
        self.rise = Output.of(self.gain.rise)
        self.pressure = Output.of(self.gain.outlet.field("p"))
        self.electricity = Output(Electricity)
        self.efficiency = Output.ratio(self.rise, self.electricity)

        # Outlets
        self.outlet = Outlet(Stream)

    def forward(self, inlets):
        """Connect the children in series; the second meter draws the line's own control."""

        # Modules
        metered = self.first(inlet=inlets.inlet, draw=1.0)
        raised = self.gain(inlet=metered.outlets.outlet, gain=self.boost)
        metered_again = self.second(inlet=raised.outlets.outlet)

        # Outlets
        outlets = dict(outlet=metered_again.outlets.outlet)
        return outlets


@pytest.fixture
def line():
    """Return a ``Line`` composite with its second meter drawing 2 W."""
    line = Line()
    line.second.draw = 2.0
    return line


class Tank(Module):
    """Pass the stream on and carry a level that rises by the inlet mass flow each step."""

    def __init__(self):
        """Declare a state, an inlet, an output and an outlet."""
        super().__init__()

        # States
        self.level = State(float, default=0.0)

        # Inlets
        self.inlet = Inlet(Stream)

        # Outputs
        self.content = Output(float)

        # Outlets
        self.outlet = Outlet(Stream)

    def forward(self, inlets):
        """Pass the stream."""

        # Outlets
        outlets = dict(outlet=inlets.inlet)
        return outlets

    def _compute_outputs(self, inlets, outlets):
        self.content = self.level + inlets.inlet.m_dot

    def _advance_states(self, inlets, outlets, dt):
        return dict(level=self.content)


class Twice(Module):
    """Call one gain twice on the same inlet and add the two pressures."""

    def __init__(self):
        """Declare the child, an inlet and an outlet."""
        super().__init__()

        # Modules
        self.gain = Gain().update_params(scale=3.0)

        # Inlets
        self.inlet = Inlet(Stream)

        # Outlets
        self.outlet = Outlet(Stream)

    def forward(self, inlets):
        """Call the child twice; both calls share its inputs."""

        # Modules
        first = self.gain(inlet=inlets.inlet)
        second = self.gain(inlet=inlets.inlet)

        # Outlets
        outlet = inlets.inlet.with_(p=first.outlets.outlet.p + second.outlets.outlet.p)
        outlets = dict(outlet=outlet)
        return outlets


@pytest.fixture
def twice():
    """Return a ``Twice`` composite."""
    return Twice()


@pytest.fixture
def tank():
    """Return a stateful ``Tank`` module."""
    return Tank()


class Chain(Module):
    """Meter, then the ``middle`` module, then a meter: the middle one can be a graph break."""

    def __init__(self, middle):
        """Declare the children, the output formulas, the drive control and the ports."""
        super().__init__()

        # Modules
        self.first = Meter()
        self.middle = middle
        self.last = Meter()

        # Inlets
        self.inlet = Inlet(Stream)

        # Controls
        self.drive = Control(float, default=1.0)

        # Outputs
        self.value = Output.of(getattr(self.middle, next(iter(middle._outputs))))
        self.pressure = Output.of(self.last.outlet.field("p"))
        self.electricity = Output(Electricity)

        # Outlets
        self.outlet = Outlet(Stream)

    def forward(self, inlets):
        """Connect the children in series; every control of the middle module gets ``drive``."""

        # Modules
        metered = self.first(inlet=inlets.inlet, draw=1.0)
        controls = {name: self.drive for name in self.middle._controls}
        through = self.middle(inlet=metered.outlets.outlet, **controls)
        last = self.last(inlet=through.outlets.outlet, draw=1.0)

        # Outlets
        outlets = dict(outlet=last.outlets.outlet)
        return outlets


class Stubborn(Gain):
    """A gain whose forward needs a number from the inlet: it cannot be traced."""

    def forward(self, inlets):
        """Raise the pressure by the gain times the inlet temperature as a plain float."""

        # Outlets
        ops.check(
            self.gain >= 0,
            PhysicsRangeError,
            "{path}: gain = {gain}",
            path=self.path,
            gain=self.gain,
        )
        outlet = inlets.inlet.with_(p=inlets.inlet.p + self.gain * float(inlets.inlet.T))
        outlets = dict(outlet=outlet)
        return outlets


class Opaque(Module):
    """A composite whose own forward needs a number from the inlet: it cannot be traced."""

    def __init__(self):
        """Declare one child, an inlet, an output to copy and an outlet."""
        super().__init__()

        # Modules
        self.meter = Meter()

        # Inlets
        self.inlet = Inlet(Stream)

        # Outputs
        self.electricity = Output(Electricity)

        # Outlets
        self.outlet = Outlet(Stream)

    def forward(self, inlets):
        """Refuse a traced value."""

        # Modules
        metered = self.meter(inlet=inlets.inlet, draw=float(inlets.inlet.T))

        # Outlets
        outlets = dict(outlet=metered.outlets.outlet)
        return outlets


class Switcher(Module):
    """Pass the stream on, but with water when the inlet is warmer than 305 K."""

    def __init__(self):
        """Declare an inlet, an output and an outlet."""
        super().__init__()

        # States
        self.level = State(float, default=0.0)

        # Inlets
        self.inlet = Inlet(Stream)

        # Outputs
        self.seen = Output(float)

        # Outlets
        self.outlet = Outlet(Stream)

    def forward(self, inlets):
        """Pass the stream; the fluid depends on the value of a row."""

        # Outlets
        fluid = WATER if inlets.inlet.T < 305.0 else BRINE
        outlets = dict(
            outlet=Stream(m_dot=inlets.inlet.m_dot, T=inlets.inlet.T, p=inlets.inlet.p, fluid=fluid)
        )
        return outlets

    def _compute_outputs(self, inlets, outlets):
        self.seen = inlets.inlet.T

    def _advance_states(self, inlets, outlets, dt):
        return dict(level=self.seen)


class Vectored(Module):
    """Pass the stream on and report the inlet pressure and one pascal more as a list."""

    def __init__(self):
        """Declare an inlet, a list output and an outlet."""
        super().__init__()

        # Inlets
        self.inlet = Inlet(Stream)

        # Outputs
        self.profile = Output(list[float])

        # Outlets
        self.outlet = Outlet(Stream)

    def forward(self, inlets):
        """Pass the stream."""

        # Outlets
        outlets = dict(outlet=inlets.inlet)
        return outlets

    def _compute_outputs(self, inlets, outlets):
        self.profile = [inlets.inlet.p, inlets.inlet.p + 1.0]


class Bounded(Module):
    """Declare a bound on a control, a boundary and three outputs: a pressure, a list, a ratio."""

    def __init__(self):
        """Declare the bounded values and the passing stream."""
        super().__init__()

        # Inlets
        self.inlet = Inlet(Stream)

        # Controls
        self.setpoint = Control(Pressure)

        # Boundaries
        self.ambient = Boundary(Temperature)

        # Outputs
        self.margin = Output(Pressure)
        self.profile = Output(list[Pressure])
        self.share = Output(Ratio | None)

        # Outlets
        self.outlet = Outlet(Stream)

    def forward(self, inlets):
        """Pass the stream."""

        # Outlets
        outlets = dict(outlet=inlets.inlet)
        return outlets

    def _compute_outputs(self, inlets, outlets):
        self.margin = inlets.inlet.p - self.setpoint
        self.profile = [self.setpoint, self.setpoint - 1.0]
        self.share = ops.where(self.ambient > 1000.0, None, self.setpoint / inlets.inlet.p)


@pytest.fixture
def bounded():
    """Return a ``Bounded`` module."""
    return Bounded()
