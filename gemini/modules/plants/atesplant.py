"""Low-temperature ATES plant: well pair, well pump, cooling heat exchanger and heat pump."""

from gemini.modules.exchangers import HeatExchanger
from gemini.modules.heating import HeatPump
from gemini.modules.piping import Mixer, Splitter
from gemini.modules.plant import Plant
from gemini.modules.pumps import CentrifugalPump
from gemini.modules.storage import AquiferStorage
from gemini.types import Inlet, Outlet, Power, Stream


class ATESPlant(Plant):
    """Seasonal ATES plant cooling a building circuit in summer and heating it in winter.

    Topology of common low-temperature ATES systems with a heat pump (Fleuchaus et al. 2018,
    "Worldwide application of aquifer thermal energy storage - A review", Renewable and
    Sustainable Energy Reviews 94, 861-876; Bloemendal and Hartog 2018, Geothermics 71,
    306-319). The season is set by three commands that move together: the ``mode`` of the
    ``storage`` and the ``split_fraction`` of ``source_valve`` and ``load_valve``, 0 for
    ``heat_exchanger`` and 1 for ``heat_pump``:

    - ``"charge"``, fractions 0 (cooling season, free cooling): groundwater from the cold well is
      pumped through the cold side of the ``heat_exchanger``, which cools the building circuit
      (``return_in`` on its hot side, ``supply_out`` its hot outlet), and is injected warmed
      into the warm well. The heat pump stands still at zero flow.
    - ``"discharge"``, fractions 1 (heating season): groundwater from the warm well is pumped
      through the evaporator (``source_in``) of the ``heat_pump`` and injected cooled into the
      cold well; the condenser heats the building circuit to the heat pump's
      ``temperature_setpoint``. The heat exchanger stands still at zero flow; the separating
      exchanger of the winter source circuit is lumped into the evaporator.
    - ``"idle"``: the charge topology with ``storage.groundwater_flow`` zero (the storage requires
      it); the building circuit passes the exchanger unchanged except for its pressure drop.

    The groundwater circuit is a loop through the well pair. ``AquiferStorage`` offers its
    produced stream at the start-of-step temperature of its source store, independent of the
    injected water, so the loop needs no iteration: ``pump`` and the exchanger or heat pump run on
    the offer and the storage is called once with the result. The storage passes pressure through
    and the well hydraulics are not modelled, so it produces at ``storage.groundwater_pressure``
    again: the pump head minus the exchanger drop is what the unmodelled wells and aquifer consume.
    The groundwater flow is a command (``storage.groundwater_flow``), as in ATES systems whose
    well-pump flow follows the building load.

    Every child is first-law closed in its own terms and the storage reports its stored heat
    as ``heat_accumulation``, so ``energy_balance`` closes except for the pump's
    ``hydraulic_power`` (flow work outside the sensible-enthalpy audit). The plant is stateful
    through its storage; ``Module.step`` steps it.

    A building block, not schedulable: ``storage.mode``, ``source_valve.split_fraction`` and
    ``load_valve.split_fraction`` move together by season and stay inputs of a run.
    """

    def __init__(self):
        """Declare the ATES children, the plant ports and the connections."""
        super().__init__()

        # Modules
        self.storage = AquiferStorage()
        self.pump = CentrifugalPump()
        self.source_valve = Splitter()
        self.load_valve = Splitter()
        self.heat_exchanger = HeatExchanger()
        self.heat_pump = HeatPump()
        self.source_mixer = Mixer()
        self.load_mixer = Mixer()

        # Inlets
        self.return_in = Inlet(Stream)
        self.power_in = Inlet(Power, kind="electricity")

        # Outlets
        self.supply_out = Outlet(Stream)
        self.loss_out = Outlet(Power, kind="heat")

        # Connections
        self.connect("return_in", "load_valve.fluid_in")
        self.connect("power_in", "pump.power_in")
        self.connect("power_in", "heat_pump.power_in")
        self.connect("storage.production_out", "pump.fluid_in")
        self.connect("pump.fluid_out", "source_valve.fluid_in")
        self.connect("source_valve.branch1_out", "heat_exchanger.cold_in")
        self.connect("load_valve.branch1_out", "heat_exchanger.hot_in")
        self.connect("source_valve.branch2_out", "heat_pump.source_in")
        self.connect("load_valve.branch2_out", "heat_pump.sink_in")
        self.connect("heat_exchanger.cold_out", "source_mixer.branch1_in")
        self.connect("heat_pump.source_out", "source_mixer.branch2_in")
        self.connect("heat_exchanger.hot_out", "load_mixer.branch1_in")
        self.connect("heat_pump.sink_out", "load_mixer.branch2_in")
        self.connect("source_mixer.fluid_out", "storage.injection_in")
        self.connect("load_mixer.fluid_out", "supply_out")
        self.connect("pump.loss_out", "loss_out")
        self.connect("storage.loss_out", "loss_out")
