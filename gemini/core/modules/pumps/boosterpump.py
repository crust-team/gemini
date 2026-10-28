"""Booster-pump passthrough with an explicit unmodelled-performance flag."""

from gemini.core.modules.module import Module
from gemini.core.types import Inlet, Outlet, Output, Stream


class BoosterPump(Module):
    """Maintains circulation pressure through the surface geothermal loop."""

    fidelity = "passthrough"

    def __init__(self):
        """Declare booster pump design data, ports and computed performance."""
        super().__init__()

        # Inlets
        self.suction = Inlet(Stream)

        # Outputs
        self.modelled = Output(bool)

        # Outlets
        self.discharge = Outlet(Stream)

    def forward(self, suction):
        """Preserve the inlet stream without implying a performance model."""
        self.modelled = False
        return suction
