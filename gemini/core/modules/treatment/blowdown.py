"""Continuous blowdown bleeding a commanded share of a circuit's flow to drain."""

from gemini.core.modules.module import Module
from gemini.core.types import Control, Fraction, Inlet, MassFlow, Outlet, Output, Stream
from gemini.errors import PhysicsRangeError


class Blowdown(Module):
    """Continuous blowdown: bleeds the share ``blowdown_fraction`` of the feed to drain.

    Blowdown limits the build-up of dissolved and suspended solids in a circuit (ASME, 1994,
    "Consensus on Operating Practices for the Control of Feedwater and Boiler Water Chemistry
    in Modern Industrial Boilers"; ASHRAE Handbook, HVAC Systems and Equipment, chapter
    "Cooling Towers", water treatment). The bleed is modelled as an ideal flow split, the share
    commanded by the blowdown valve or conductivity controller:

    - ``blowdown_out.m_dot = blowdown_fraction * feed_in.m_dot``;
    - ``retained_out.m_dot = feed_in.m_dot - blowdown_out.m_dot``.

    Both outlets keep the feed temperature, pressure and fluid: the valve pressure loss and any
    flash of the drained water are not modelled. The drained stream carries its own enthalpy, so
    there is no ``heat_loss`` output: when ``blowdown_out`` leaves the plant, the stream audit
    counts it as an outflow, and mass and sensible energy close exactly. The fraction is a
    control because operators and controllers adjust it to the measured concentration (for a
    make-up stream ``M`` and ``C`` cycles of concentration the bleed is ``M / C``). Reverse
    flow through a blowdown is not defined and raises ``PhysicsRangeError``.
    """

    def __init__(self):
        """Declare the feed, the bleed command and both outlets."""
        super().__init__()

        # Inlets
        self.feed_in = Inlet(Stream)

        # Controls
        self.blowdown_fraction = Control(Fraction)

        # Outputs
        self.blowdown_mass_flow = Output(MassFlow)

        # Outlets
        self.retained_out = Outlet(Stream)
        self.blowdown_out = Outlet(Stream)

    def forward(self, inlets):
        """Split the commanded bleed from the feed."""

        # Outlets
        feed_in = inlets.feed_in
        if feed_in.m_dot < 0:
            raise PhysicsRangeError(
                f"{self.path}: feed_in.m_dot = {feed_in.m_dot} kg/s; expected >= 0"
            )
        bleed = self.blowdown_fraction * feed_in.m_dot
        retained_out = feed_in.with_(m_dot=feed_in.m_dot - bleed)
        blowdown_out = feed_in.with_(m_dot=bleed)

        outlets = dict(retained_out=retained_out, blowdown_out=blowdown_out)
        return outlets

    def _compute_outputs(self, inlets, outlets):
        self.blowdown_mass_flow = outlets.blowdown_out.m_dot
