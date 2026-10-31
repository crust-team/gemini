"""The plant's edge for discarded flows."""

from gemini.modules.module import Module
from gemini.types import Inlet, Stream


class WasteGrid(Module):
    """Where blowdown, sand and other discarded flows leave the plant.

    ``waste_in`` takes any number of connections. What leaves is read from the port; the disposal
    cost per kg is ``waste_disposal_price`` of ``gm.economics.Assumptions``.
    """

    def __init__(self):
        """Declare the port of the discarded flows."""
        super().__init__()

        # Inlets
        self.waste_in = Inlet(Stream, kind="waste", many=True)

    def forward(self, inlets):
        """End the flows here."""

        outlets = dict()
        return outlets
