"""Booster-pump passthrough with an explicit unmodelled-performance flag."""

from gemini.core.modules.module import Module
from gemini.core.types import Inlet, Outlet, Output, Stream


class BoosterPump(Module):
    """Booster pump placeholder: passes the stream through unchanged; ``modelled`` is False."""

    def __init__(self):
        """Declare the ports and the unmodelled-performance flag."""
        super().__init__()

        # Inlets
        self.suction = Inlet(Stream)

        # Outputs
        self.modelled = Output(bool)

        # Outlets
        self.discharge = Outlet(Stream)

    def forward(self, inlets):
        """Preserve the inlet stream without implying a performance model."""

        # Outlets
        suction = inlets.suction
        discharge = suction

        outlets = dict(discharge=discharge)
        return outlets

    def _compute_outputs(self, inlets, outlets):
        self.modelled = False
