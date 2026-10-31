"""Nodal doublet with three parallel heat exchangers on one secondary network."""

from gemini.modules.container import ModuleList
from gemini.modules.exchangers import HeatExchanger
from gemini.modules.grids import ElectricityGrid
from gemini.modules.module import Module
from gemini.modules.piping import Mixer, Splitter
from gemini.modules.plants.nodaldoublet import NodalDoublet
from gemini.modules.treatment import Degasser, Filter
from gemini.types import Inlet, Outlet, Output, Stream

SHARES = (0.5, 0.3, 0.2)
"""Shares of the primary and the secondary flow sent to each heat exchanger."""


class ParallelExchangerPlant(Module):
    """Nodal doublet whose brine heats one secondary network through three parallel exchangers.

    The port of the upstream GEMINI simulator's ``parallel_hex_plant`` example. The producer is
    solved for its rate at the ``doublet.wellhead_pressure`` boundary; the brine passes a degasser
    and a filter, is divided over the exchangers in ``SHARES``, remixed, filtered again and
    injected, with the injection pump set to the wellhead pressure the injector needs. The
    secondary water is divided in the same shares, set as the ``split_fraction`` of the two
    splitter cascades, and remixed after the exchangers. ``gm.plants.example`` carries the well,
    reservoir, ESP and exchanger data of the upstream example.
    """

    def __init__(self):
        """Build the plant; the tees are cascades of two-way splitters and mixers."""
        super().__init__()

        # Modules
        self.doublet = NodalDoublet()
        self.degasser = Degasser()
        self.inlet_filter = Filter()
        self.primary_splitters = ModuleList(Splitter() for _ in SHARES[1:])
        self.secondary_splitters = ModuleList(Splitter() for _ in SHARES[1:])
        self.heat_exchangers = ModuleList(HeatExchanger() for _ in SHARES)
        self.primary_mixers = ModuleList(Mixer() for _ in SHARES[1:])
        self.secondary_mixers = ModuleList(Mixer() for _ in SHARES[1:])
        self.outlet_filter = Filter()
        self.electricity_grid = ElectricityGrid()

        # Inlets
        self.return_in = Inlet(Stream)

        # Outputs
        self.production_rate = Output.of(self.doublet.riser.wellhead_out.field("m_dot"))
        self.injection_pressure = Output.of(self.doublet.injection_pump.discharge_pressure)
        self.injection_pump_power = Output.of(self.doublet.injection_pump.power)
        self.supply_out_T = Output.of(self.secondary_mixers[len(SHARES) - 2].fluid_out.field("T"))

        # Outlets
        self.supply_out = Outlet(Stream)

    def forward(self, inlets):
        """Produce and treat the brine, exchange in parallel, remix and inject it."""

        # Modules
        supply, lift_power, well_losses = self.doublet.produce()
        degassed = self.degasser(fluid_in=supply)
        filtered = self.inlet_filter(fluid_in=degassed.outlets.liquid_out)
        primaries = divide(self.primary_splitters, filtered.outlets.fluid_out)
        secondaries = divide(self.secondary_splitters, inlets.return_in)
        exchanged = [
            exchanger(hot_in=hot, cold_in=cold)
            for exchanger, hot, cold in zip(self.heat_exchangers, primaries, secondaries)
        ]
        cooled = combine(self.primary_mixers, [each.outlets.hot_out for each in exchanged])
        returned = self.outlet_filter(fluid_in=cooled)
        injection_power, injection_loss = self.doublet.inject(returned.outlets.fluid_out)
        self.doublet.formation(heat_in=well_losses + injection_loss)
        self.electricity_grid(power_in=[], power_out=[lift_power, injection_power])

        # Outlets
        supply_out = combine(self.secondary_mixers, [each.outlets.cold_out for each in exchanged])

        outlets = dict(supply_out=supply_out)
        return outlets


def divide(splitters, stream):
    """Return the branches of a splitter cascade: each splitter sends its share to a branch."""
    branches = []
    for splitter in splitters:
        split = splitter(fluid_in=stream)
        branches.append(split.outlets.branch2_out)
        stream = split.outlets.branch1_out
    return branches + [stream]


def combine(mixers, streams):
    """Return the stream a mixer cascade makes of ``streams``, the running mix entering first."""
    mixed = streams[0]
    for mixer, stream in zip(mixers, streams[1:]):
        mixed = mixer(branch1_in=mixed, branch2_in=stream).outlets.fluid_out
    return mixed
