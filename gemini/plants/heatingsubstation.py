"""Building heating substation: valve, heat exchanger, the building's demand and its pump."""

from gemini.modules.declarations import Inlet, Outlet
from gemini.modules.exchangers import HeatExchanger
from gemini.modules.grids import HeatingGrid
from gemini.modules.piping import Valve
from gemini.modules.pumps import CirculationPump
from gemini.plants.plant import Plant
from gemini.types import Power, Stream


class HeatingSubstation(Plant):
    """Indirect district-heating substation serving a building heating circuit.

    The network water passes the control ``valve`` and the hot side of the ``heat_exchanger``;
    the building circuit, a closed loop inside the substation, passes its cold side, the
    ``consumer`` (a ``HeatingGrid`` with the building's ``heat_demand``) and the ``pump``, which
    sets its flow and its pressure and draws the electricity for it through ``power_in``. This is
    the common indirect connection of district heating customers (Frederiksen and Werner 2013,
    *District Heating and Cooling*, Studentlitteratur).

    The building loop closes within one call: the plant tears it at ``consumer.return_out``,
    starts at the consumer's ``minimum_return_temperature`` and never exceeds the network
    temperature after the valve, where the exchanger would reverse. A stopped network transfers
    no heat.

    The valve only throttles: the network flow is imposed by ``supply_in`` (in a
    ``DistrictNetwork`` by its splitters), and the valve reports the pressure drop that flow
    causes at the commanded ``valve.opening``. Every child is first-law closed and the building
    loop passes the same mass flow, so ``energy_balance`` closes; the converged loop still
    differs by at most the tolerance between the consumer's return and the stream fed back,
    which therefore appear as a boundary pair in the audit's ``in`` and ``out``.

    Valid in the ranges of the children: liquid circuits, forward flow, a network supply at
    least as warm as the building return.

    A building block, not schedulable on its own: a run sets ``valve.opening`` and the demand.
    """

    def __init__(self):
        """Declare the substation children, its ports and the circuits."""
        super().__init__()

        # Modules
        self.valve = Valve()
        self.heat_exchanger = HeatExchanger()
        self.consumer = HeatingGrid()
        self.pump = CirculationPump()

        # Inlets
        self.supply_in = Inlet(Stream, kind="hot_water")
        self.power_in = Inlet(Power, kind="electricity")

        # Outlets
        self.return_out = Outlet(Stream, kind="hot_water")
        self.loss_out = Outlet(Power, kind="heat")

        # Connections
        self.connect("supply_in", "valve.fluid_in")
        self.connect("power_in", "pump.power_in")
        self.connect("valve.fluid_out", "heat_exchanger.hot_in")
        self.connect("heat_exchanger.hot_out", "return_out")
        self.connect("heat_exchanger.cold_out", "consumer.supply_in")
        self.connect("consumer.return_out", "pump.fluid_in")
        self.connect("pump.fluid_out", "heat_exchanger.cold_in")
        self.connect("pump.loss_out", "loss_out")
