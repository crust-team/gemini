"""Geothermal well field with several production and injection limbs."""

from gemini.core.modules.container import ModuleDict, ModuleList
from gemini.core.modules.module import Module
from gemini.core.modules.piping import Mixer, Splitter
from gemini.core.modules.pumps import ESP
from gemini.core.modules.subsurface import (
    InjectionReservoir,
    InjectionWell,
    ProductionReservoir,
    ProductionWell,
)
from gemini.core.types import Inlet, Outlet, Output, Stream
from gemini.errors import ConfigurationError


class MultiWellPlant(Module):
    """Well field producing from several wells into one supply and injecting into several.

    The structural arguments are the numbers of limbs: ``producers`` (default 2) production
    limbs, each a ``ModuleDict`` of ``reservoir`` (``ProductionReservoir``), lower ``well``
    (``ProductionWell``), ``esp`` and ``riser`` (``ProductionWell``) traversed like the
    production limb of ``Doublet``, and ``injectors`` (default 1) injection limbs, each a
    ``ModuleDict`` of ``well`` (``InjectionWell``) and ``sink`` (``InjectionReservoir``). Paths
    read like ``producers.0.esp.frequency`` or ``injectors.1.sink.injectivity_index``.

    The wellhead streams are joined by a cascade of ``producers - 1`` adiabatic two-way
    ``Mixer``s, the running mix entering ``first_in`` of the next mixer. Capacity-rate weighting
    is associative, so the cascade gives the N-way mixing temperature
    ``sum(m_i cp_i T_i) / sum(m_i cp_i)``, and its pressure is the lowest wellhead pressure (each
    mixer takes the lower inlet pressure; the other wells are throttled to it). ``return_in`` is
    divided by a cascade of ``injectors - 1`` ``Splitter``s: splitter ``i`` sends its
    ``split_fraction`` of the flow reaching it to injector ``i`` and passes the rest on; the last
    injector takes what remains, so injector ``i`` receives ``f_i * prod_{j < i} (1 - f_j)`` of
    the return flow (equal shares need ``f_i = 1 / (M - i)``). The splitters stand for the
    wellhead chokes or the injection-pump allocation of the field.

    As in ``Doublet`` the return boundary is independent of the production in one call; the
    field's mass balance is held by the reservoirs' ``production_rate`` controls and the
    caller. Outputs are the totals of ``electricity`` and ``heat_loss`` over every leaf and the
    supply temperature.
    """

    def __init__(self, producers=2, injectors=1):
        """Build ``producers`` production limbs, ``injectors`` injection limbs and the tees."""
        super().__init__()
        if producers < 1 or injectors < 1:
            raise ConfigurationError(
                f"{self.path}: producers = {producers}, injectors = {injectors}; expected >= 1"
            )

        # Modules
        self.producers = ModuleList(_production_limb() for _ in range(producers))
        self.mixers = ModuleList(Mixer() for _ in range(producers - 1))
        self.splitters = ModuleList(Splitter() for _ in range(injectors - 1))
        self.injectors = ModuleList(_injection_limb() for _ in range(injectors))

        # Inlets
        self.return_in = Inlet(Stream)

        # Outputs
        self.electricity = Output.total("electricity")
        self.heat_loss = Output.total("heat_loss")
        if producers > 1:
            self.supply_out_T = Output.of(f"mixers.{producers - 2}.mixed_out_T")
        else:
            self.supply_out_T = Output.of("producers.0.riser.wellhead_temperature")

        # Outlets
        self.supply_out = Outlet(Stream)

    def forward(self, inlets):
        """Produce and mix every production limb, then split the return over the injectors."""

        # Modules
        supply = self.collect([self.produce(limb) for limb in self.producers])
        self.inject(inlets.return_in)

        # Outlets
        supply_out = supply

        outlets = dict(supply_out=supply_out)
        return outlets

    @staticmethod
    def produce(limb):
        """Traverse one production limb: reservoir, lower well, ESP and riser."""
        source = limb.reservoir()
        lower = limb.well(bottom=source.outlets.sandface)
        pump = limb.esp(suction=lower.outlets.wellhead)
        upper = limb.riser(bottom=pump.outlets.discharge)
        return upper.outlets.wellhead

    def collect(self, streams):
        """Mix the wellhead streams through the mixer cascade into one supply stream."""
        mixed = streams[0]
        for mixer, stream in zip(self.mixers, streams[1:]):
            mixed = mixer(first_in=mixed, second_in=stream).outlets.mixed_out
        return mixed

    def inject(self, stream):
        """Split ``stream`` through the splitter cascade into the injection limbs."""
        for splitter, limb in zip(self.splitters, self.injectors):
            split = splitter(feed_in=stream)
            _inject(limb, split.outlets.second_out)
            stream = split.outlets.first_out
        _inject(self.injectors[len(self.splitters)], stream)


def _production_limb():
    """Return the unconfigured children of one production limb."""
    return ModuleDict(
        {
            "reservoir": ProductionReservoir(),
            "well": ProductionWell(),
            "esp": ESP(),
            "riser": ProductionWell(),
        }
    )


def _injection_limb():
    """Return the unconfigured children of one injection limb."""
    return ModuleDict({"well": InjectionWell(), "sink": InjectionReservoir()})


def _inject(limb, stream):
    """Traverse one injection limb: injection well and receiving aquifer."""
    injection = limb.well(wellhead=stream)
    limb.sink(sandface=injection.outlets.bottom)
