"""Example doublet heat plant with every connection written explicitly."""

from gemini.core.modules import Module, ModuleDict
from gemini.core.modules.heat import HeatExchanger
from gemini.core.modules.plants import Doublet
from gemini.core.modules.pumps import InjectionPump
from gemini.core.modules.treatment import Degasser, Filter
from gemini.core.types import (
    Inlet,
    Outlet,
    Output,
    Stream,
)


class DoubletHeatPlant(Module):
    """Doublet, degasser, filters, heat exchanger and injection pump in diagram order."""

    def __init__(self):
        """Declare the complete plant tree, ports and outputs."""
        super().__init__()

        # Modules
        self.doublet = Doublet()
        self.degasser = Degasser()
        self.filters = ModuleDict({"hot": Filter(), "cold": Filter()})
        self.heat_exchanger = HeatExchanger()
        self.injection_pump = InjectionPump()

        # Inlets
        self.secondary_in = Inlet(Stream)

        # Outputs
        self.thermal_power = Output.of("heat_exchanger.duty")
        self.electricity_use = Output.total("electricity")
        self.cop = Output.ratio("thermal_power", "electricity_use")
        self.heat_loss = Output.total("heat_loss")

        # Outlets
        self.secondary_out = Outlet(Stream)
        self.gas = Outlet(Stream)

    def forward(self, inlets):
        """Connect the doublet limbs through the modeled surface equipment."""

        # Modules
        supply = self.doublet.produce()
        degassed = self.degasser(inlet=supply)
        filtered = self.filters.hot(inlet=degassed.outlets.liquid)
        exchanged = self.heat_exchanger(hot_in=filtered.outlets.outlet, cold_in=inlets.secondary_in)
        returned = self.filters.cold(inlet=exchanged.outlets.hot_out)
        pumped = self.injection_pump(suction=returned.outlets.outlet)
        self.doublet.inject(pumped.outlets.discharge)

        # Outlets
        secondary_out = exchanged.outlets.cold_out
        gas = degassed.outlets.gas

        outlets = dict(secondary_out=secondary_out, gas=gas)
        return outlets
