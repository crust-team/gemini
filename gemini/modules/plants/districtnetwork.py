"""A two-pipe network feeding parallel substations."""

from gemini.errors import ValidationError
from gemini.modules.container import ModuleList
from gemini.modules.piping import Mixer, Pipe, Splitter
from gemini.modules.plant import Plant
from gemini.modules.plants.coolingsubstation import CoolingSubstation
from gemini.modules.plants.heatingsubstation import HeatingSubstation
from gemini.modules.pumps import CentrifugalPump
from gemini.types import Inlet, Outlet, Power, Stream

SUBSTATIONS = {"heating": HeatingSubstation, "cooling": CoolingSubstation}
"""Substation class per network service."""


class DistrictNetwork(Plant):
    """A two-pipe network feeding ``consumers`` parallel substations.

    Flow order: ``pump``, ``supply_pipe``, ``splitters``, ``substations``, ``mixers``,
    ``return_pipe``. ``service`` is ``"heating"`` or ``"cooling"``, the substation class. The
    network pumps, splits, serves the substations in order, mixes the returns and passes the
    return pipe.
    """

    def __init__(self, consumers=2, service="heating"):
        """Build a network of the given size; both are structural arguments."""
        super().__init__()
        if service not in SUBSTATIONS:
            raise ValidationError(
                f"service = {service!r}; expected 'heating' or 'cooling'", code="invalid_design"
            )
        if consumers < 1:
            raise ValidationError(f"consumers = {consumers}; expected >= 1", code="invalid_design")
        self._size = {"consumers": consumers, "service": service}

        # Modules
        self.pump = CentrifugalPump()
        self.supply_pipe = Pipe()
        self.splitters = ModuleList(Splitter() for _ in range(consumers - 1))
        self.substations = ModuleList(SUBSTATIONS[service]() for _ in range(consumers))
        self.mixers = ModuleList(Mixer() for _ in range(consumers - 1))
        self.return_pipe = Pipe()

        # Inlets
        self.supply_in = Inlet(Stream)
        self.power_in = Inlet(Power, kind="electricity")
        self.air_in = Inlet(Stream, kind="air")

        # Outlets
        self.return_out = Outlet(Stream)
        self.loss_out = Outlet(Power, kind="heat")

        # Connections
        self.connect("supply_in", "pump.fluid_in")
        self.connect("power_in", "pump.power_in")
        self.connect("air_in", "supply_pipe.air_in")
        self.connect("air_in", "return_pipe.air_in")
        self.connect("pump.fluid_out", "supply_pipe.fluid_in")
        self._connect_feed(consumers)
        self._connect_returns(consumers)
        self.connect("return_pipe.fluid_out", "return_out")
        for index in range(consumers):
            self.connect("power_in", f"substations.{index}.power_in")
            self.connect(f"substations.{index}.loss_out", "loss_out")
        self.connect("pump.loss_out", "loss_out")
        self.connect("supply_pipe.loss_out", "loss_out")
        self.connect("return_pipe.loss_out", "loss_out")

    def _connect_feed(self, consumers):
        """Divide the feed over the substations: each splitter serves one, the last what is left."""
        count = consumers - 1
        if count == 0:
            self.connect("supply_pipe.fluid_out", "substations.0.supply_in")
            return
        self.connect("supply_pipe.fluid_out", "splitters.0.fluid_in")
        for index in range(count - 1):
            self.connect(f"splitters.{index}.branch1_out", f"splitters.{index + 1}.fluid_in")
        for index in range(count):
            self.connect(f"splitters.{index}.branch2_out", f"substations.{index}.supply_in")
        self.connect(f"splitters.{count - 1}.branch1_out", f"substations.{count}.supply_in")

    def _connect_returns(self, consumers):
        """Mix the returns of the substations in order and feed the return pipe."""
        running = "substations.0.return_out"
        for index in range(consumers - 1):
            self.connect(running, f"mixers.{index}.branch1_in")
            self.connect(f"substations.{index + 1}.return_out", f"mixers.{index}.branch2_in")
            running = f"mixers.{index}.fluid_out"
        self.connect(running, "return_pipe.fluid_in")
