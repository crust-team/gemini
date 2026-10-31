"""Continuous blowdown bleeding a commanded share of a circuit's flow to drain."""

from gemini import ops
from gemini.errors import PhysicsError
from gemini.modules.module import Module
from gemini.physics import separation
from gemini.types import Control, Fraction, Inlet, MassFlow, Outlet, Output, Stream


class Blowdown(Module):
    """Continuous blowdown: bleeds the share ``blowdown_fraction`` of the feed to drain.

    Blowdown limits the build-up of dissolved and suspended solids in a circuit (ASME, 1994,
    "Consensus on Operating Practices for the Control of Feedwater and Boiler Water Chemistry
    in Modern Industrial Boilers"; ASHRAE Handbook, HVAC Systems and Equipment, chapter
    "Cooling Towers", water treatment). The bleed is modelled as an ideal flow split, the share
    commanded by the blowdown valve or conductivity controller:

    - ``waste_out.m_dot = blowdown_fraction * fluid_in.m_dot``;
    - ``fluid_out.m_dot = fluid_in.m_dot - waste_out.m_dot``.

    Both outlets keep the feed temperature, pressure and fluid: the valve pressure loss and any
    flash of the drained water are not modelled. The drained stream carries its own enthalpy, so
    there is no ``heat_loss`` output: when ``waste_out`` leaves the plant, the stream audit
    counts it as an outflow, and mass and sensible energy close exactly. The fraction is a
    control because operators and controllers adjust it to the measured concentration (for a
    make-up stream ``M`` and ``C`` cycles of concentration the bleed is ``M / C``). Reverse
    flow through a blowdown is not defined and raises ``PhysicsError``.
    """

    def __init__(self):
        """Declare the feed, the bleed command and both outlets."""
        super().__init__()

        # Inlets
        self.fluid_in = Inlet(Stream, kind="brine")

        # Controls
        self.blowdown_fraction = Control(Fraction)

        # Outputs
        self.blowdown_mass_flow = Output(MassFlow)

        # Outlets
        self.fluid_out = Outlet(Stream, kind="brine")
        self.waste_out = Outlet(Stream, kind="waste")

    def forward(self, inlets):
        """Split the commanded bleed from the feed."""

        # Outlets
        fluid_in = inlets.fluid_in
        ops.check(
            fluid_in.m_dot >= 0,
            PhysicsError,
            "{path}: fluid_in.m_dot = {m_dot} kg/s; expected >= 0",
            path=self.path,
            m_dot=fluid_in.m_dot,
        )
        retained, bleed = separation.split_flow(fluid_in.m_dot, self.blowdown_fraction)
        fluid_out = fluid_in.with_(m_dot=retained)
        waste_out = fluid_in.with_(m_dot=bleed)

        outlets = dict(fluid_out=fluid_out, waste_out=waste_out)
        return outlets

    def _compute_outputs(self, inlets, outlets):
        self.blowdown_mass_flow = outlets.waste_out.m_dot
