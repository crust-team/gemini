"""Small user-defined plant using a ModuleList."""

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
        inlet = inlets.inlet
        filtered = self._apply_filters(inlet)

        # Outlets
        outlet = filtered

        outlets = dict(outlet=outlet)
        return outlets

    def _apply_filters(self, inlet):
        stream = inlet
        for filter_ in self.filters:
            stream = filter_(inlet=stream).outlets.outlet
        return stream


plant = TreatmentTrain()
result = plant(inlet=gm.Stream(flow="10 kg/s", T="60 C", p="10 bar"))
print(result.outlets.outlet)
