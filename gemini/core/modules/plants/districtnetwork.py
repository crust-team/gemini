"""District heating or cooling network: circulation pump, pipes and parallel substations."""

from gemini.core.modules.container import ModuleList
from gemini.core.modules.module import Module
from gemini.core.modules.piping import Mixer, Pipe, Splitter
from gemini.core.modules.plants.coolingsubstation import CoolingSubstation
from gemini.core.modules.plants.heatingsubstation import HeatingSubstation
from gemini.core.modules.pumps import CentrifugalPump
from gemini.core.types import Inlet, Outlet, Output, Stream
from gemini.errors import ConfigurationError

SUBSTATIONS = {"heating": HeatingSubstation, "cooling": CoolingSubstation}
"""Substation class per network service."""


class DistrictNetwork(Module):
    """Two-pipe district network feeding parallel substations from one supply.

    Flow order: ``supply_in`` -> circulation ``pump`` -> ``supply_pipe`` -> splitter cascade ->
    ``substations`` in parallel -> mixer cascade -> ``return_pipe`` -> ``return_out``. The
    structural arguments are the number of substations ``consumers`` (default 2) and the
    ``service``: ``"heating"`` builds ``HeatingSubstation`` children and ``"cooling"``
    ``CoolingSubstation`` children, the same choice the two substation classes make.

    The supply is divided by a cascade of ``consumers - 1`` two-way ``Splitter``s: splitter
    ``i`` sends its ``split_fraction`` of the flow reaching it to substation ``i`` and passes the
    rest on, and the last substation takes what remains. Substation ``i`` therefore receives
    ``f_i * prod_{j < i} (1 - f_j)`` of the supply; equal shares need ``f_i = 1 / (N - i)``.
    The splitters stand for the balancing valves and branch resistances of the real network;
    the model does not solve the network hydraulics, and each substation's valve reports the
    pressure drop its share causes. The returns are joined by a cascade of ``consumers - 1``
    adiabatic ``Mixer``s, the running mix entering ``first_in``; capacity-rate weighting is
    associative, so the cascade gives the N-way mixing temperature, at the lowest return
    pressure. Supply and return pipes lump the network's distribution losses (or gains) to their
    ``ambient_temperature``.

    Every child is first-law closed in its own terms. ``energy_balance`` audits sensible
    enthalpy only, so its residual for the network is the pump's ``hydraulic_power`` (the flow
    work that the pipe and valve pressure drops dissipate without a modelled temperature rise);
    the thermal model is otherwise closed. Mass is conserved.
    """

    def __init__(self, consumers=2, service="heating"):
        """Build the pump, both pipes, ``consumers`` substations of ``service`` and the tees."""
        super().__init__()
        if service not in SUBSTATIONS:
            raise ConfigurationError(
                f"{self.path}: service = {service!r}; expected 'heating' or 'cooling'"
            )
        if consumers < 1:
            raise ConfigurationError(f"{self.path}: consumers = {consumers}; expected >= 1")

        # Modules
        self.pump = CentrifugalPump()
        self.supply_pipe = Pipe()
        self.splitters = ModuleList(Splitter() for _ in range(consumers - 1))
        self.substations = ModuleList(SUBSTATIONS[service]() for _ in range(consumers))
        self.mixers = ModuleList(Mixer() for _ in range(consumers - 1))
        self.return_pipe = Pipe()

        # Inlets
        self.supply_in = Inlet(Stream)

        # Outputs
        if service == "heating":
            self.heat_supplied = Output.total("heat_supplied")
        self.heat_absorbed = Output.total("heat_absorbed")
        self.heat_loss = Output.total("heat_loss")
        self.electricity = Output.total("electricity")
        self.return_out_T = Output.of("return_pipe.outlet_T")

        # Outlets
        self.return_out = Outlet(Stream)

    def forward(self, inlets):
        """Pump and distribute the supply, serve every substation and collect the returns."""

        # Modules
        pumped = self.pump(suction=inlets.supply_in)
        supplied = self.supply_pipe(inlet=pumped.outlets.discharge)
        returns = [
            substation(network_in=feed).outlets.network_out
            for substation, feed in zip(self.substations, self.distribute(supplied.outlets.outlet))
        ]
        returned = self.return_pipe(inlet=self.collect(returns))

        # Outlets
        return_out = returned.outlets.outlet

        outlets = dict(return_out=return_out)
        return outlets

    def distribute(self, supply):
        """Split ``supply`` through the splitter cascade; return one feed per substation."""
        feeds = []
        for splitter in self.splitters:
            split = splitter(feed_in=supply)
            feeds.append(split.outlets.second_out)
            supply = split.outlets.first_out
        return feeds + [supply]

    def collect(self, returns):
        """Mix the substation returns through the mixer cascade into one stream."""
        mixed = returns[0]
        for mixer, stream in zip(self.mixers, returns[1:]):
            mixed = mixer(first_in=mixed, second_in=stream).outlets.mixed_out
        return mixed
