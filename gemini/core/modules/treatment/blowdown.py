"""Blowdown placeholder that conserves the incoming stream."""

from gemini.core.modules.module import Module
from gemini.core.types import Inlet, Outlet, Output, Stream


class Blowdown(Module):
    """Blowdown placeholder: passes the stream through unchanged; ``modelled`` is False."""

    def __init__(self):
        """Declare the ports and the unmodelled-performance flag."""
        super().__init__()

        # Inlets
        self.inlet = Inlet(Stream)

        # Outputs
        self.modelled = Output(bool)

        # Outlets
        self.outlet = Outlet(Stream)

    def forward(self, inlets):
        """Preserve the inlet stream without implying a performance model."""

        # Outlets
        inlet = inlets.inlet
        outlet = inlet

        outlets = dict(outlet=outlet)
        return outlets

    def _compute_outputs(self, inlets, outlets):
        self.modelled = False
