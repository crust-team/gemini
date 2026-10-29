"""Small user-defined plant using a ModuleList.

Run from the repository root: PYTHONPATH=. python examples/core/basics/02_custom_plant.py
"""

import gemini as gm
from gemini.core.types import Inlet, Outlet, Stream


class TreatmentTrain(gm.modules.Module):
    """Pass a stream through a structural list of filters."""

    def __init__(self, count=2):
        """Build a structural sequence with the requested number of filters."""
        super().__init__()

        # Modules
        self.filters = gm.modules.ModuleList(gm.modules.Filter() for _ in range(count))

        # Inlets
        self.inlet = Inlet(Stream)

        # Outlets
        self.outlet = Outlet(Stream)

    def forward(self, inlets):
        """Apply each filter in diagram order."""

        # Modules
        filtered = self._apply_filters(inlets.inlet)

        # Outlets
        outlets = dict(outlet=filtered)
        return outlets

    def _apply_filters(self, stream):
        """Pass the stream through every filter in list order."""
        for module in self.filters:
            stream = module(inlet=stream).outlets.outlet
        return stream


plant = TreatmentTrain()
result = plant(inlet=gm.Stream(flow="10 kg/s", T="60 C", p="10 bar"))
print(result.outlets.outlet)
