"""Reusable production and reinjection limbs of a geothermal doublet."""

from gemini.core.modules.module import Module
from gemini.core.modules.pumps import ESP
from gemini.core.modules.subsurface import (
    InjectionReservoir,
    InjectionWell,
    ProductionReservoir,
    ProductionWell,
)
from gemini.core.types import (
    Inlet,
    Outlet,
    Output,
    Stream,
)


class Doublet(Module):
    """Produce hot supply and return cooled brine to the receiving aquifer."""

    def __init__(self):
        """Build the production-to-injection doublet in flow order."""
        super().__init__()

        # Modules
        self.reservoir = ProductionReservoir()
        self.well = ProductionWell()
        self.esp = ESP()
        self.riser = ProductionWell()
        self.injector = InjectionWell()
        self.sink = InjectionReservoir()

        # Inlets
        self.return_stream = Inlet(Stream)

        # Outputs
        self.electricity = Output.total("electricity")
        self.heat_loss = Output.total("heat_loss")

        # Outlets
        self.supply = Outlet(Stream)

    def produce(self):
        """Traverse reservoir, lower well, ESP and riser."""
        source = self.reservoir()
        lower = self.well(bottom=source.outlets.sandface)
        pump = self.esp(suction=lower.outlets.wellhead)
        upper = self.riser(bottom=pump.outlets.discharge)
        return upper.outlets.wellhead

    def inject(self, stream):
        """Traverse the injection well and receiving aquifer."""
        injection = self.injector(wellhead=stream)
        self.sink(sandface=injection.outlets.bottom)

    def forward(self, return_stream):
        """Evaluate both limbs for an independently specified return boundary."""

        # Modules
        produced_supply = self.produce()
        self.inject(return_stream)

        # Outlets
        supply = produced_supply

        outlets = dict(supply=supply)
        return outlets
