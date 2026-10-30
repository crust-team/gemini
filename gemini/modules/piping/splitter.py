"""Flow splitter dividing one stream into two branches."""

from gemini import ops
from gemini.errors import PhysicsError
from gemini.modules.module import Module
from gemini.physics import separation
from gemini.types import Control, Fraction, Inlet, Outlet, Stream


class Splitter(Module):
    """Ideal tee dividing a feed into two branches at the commanded mass-flow split.

    ``second_out`` carries ``split_fraction * m_dot`` and ``first_out`` the rest; both keep the
    feed temperature, pressure and fluid. The tee has no pressure loss or heat exchange (put a
    ``Pipe`` or ``Valve`` in a branch for those), so mass and energy close to rounding. The
    commanded split stands for whatever sets it in the plant (balancing valves, branch
    resistances); the splitter does not solve a hydraulic network. Reverse flow (``m_dot < 0``)
    raises ``PhysicsError``: a reversed splitter is a ``Mixer``.
    """

    def __init__(self):
        """Declare the feed, the split command and both branch outlets."""
        super().__init__()

        # Inlets
        self.feed_in = Inlet(Stream)

        # Controls
        self.split_fraction = Control(Fraction)

        # Outlets
        self.first_out = Outlet(Stream)
        self.second_out = Outlet(Stream)

    def forward(self, inlets):
        """Divide the feed mass flow between the two branches."""

        # Outlets
        feed_in = inlets.feed_in
        ops.check(
            feed_in.m_dot >= 0,
            PhysicsError,
            "{path}: feed_in.m_dot = {m_dot} kg/s; expected >= 0 (reverse flow "
            "is not modelled; use a Mixer)",
            path=self.path,
            m_dot=feed_in.m_dot,
        )
        first_flow, second_flow = separation.split_flow(feed_in.m_dot, self.split_fraction)
        first_out = feed_in.with_(m_dot=first_flow)
        second_out = feed_in.with_(m_dot=second_flow)

        outlets = dict(first_out=first_out, second_out=second_out)
        return outlets
