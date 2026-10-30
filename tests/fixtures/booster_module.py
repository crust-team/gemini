"""A small valid module in a file of its own, as a user would write and load one."""

from gemini.core.modules.module import Module
from gemini.core.types import Inlet, Outlet, Output, Parameter, Pressure, PressureDifference, Stream


class Booster(Module):
    """Raise the stream pressure by a fixed gain."""

    category = "pump"

    def __init__(self):
        """Declare the gain, the suction and discharge ports and the head."""
        super().__init__()

        # Parameters
        self.gain = Parameter(PressureDifference, default=1e5)

        # Inlets
        self.suction = Inlet(Stream)

        # Outputs
        self.head = Output(Pressure)

        # Outlets
        self.discharge = Outlet(Stream)

    def forward(self, inlets):
        """Return the suction stream at a pressure raised by the gain."""

        # Outlets
        discharge = inlets.suction.with_(p=inlets.suction.p + self.gain)

        outlets = dict(discharge=discharge)
        return outlets

    def _compute_outputs(self, inlets, outlets):
        self.head = self.gain


EXAMPLE = {"inlets": {"suction": {"m_dot": "10 kg/s", "T": "50 degC", "p": "2 bar"}}}
"""Values for one call of ``Booster``, the arguments of ``gm.evaluate``."""
