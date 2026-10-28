"""Blowdown placeholder that conserves the incoming stream."""

from gemini.core.modules.module import Module
from gemini.core.types import Inlet, Outlet, Output, Stream


class Blowdown(Module):
    """Removes a controlled fraction of circulating brine."""

    fidelity = "passthrough"

    def __init__(self):
        """Declare blowdown fraction, inlet and split outlets."""
        super().__init__()

        # Inlets
        self.inlet = Inlet(Stream)

        # Outputs
        self.modelled = Output(bool)

        # Outlets
        self.outlet = Outlet(Stream)

    def forward(self, inlet):
        """Preserve the inlet stream without implying a performance model."""
        self.modelled = False
        return inlet
