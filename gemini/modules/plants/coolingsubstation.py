"""Building cooling substation: valve, heat exchanger, the building's loads and its pump."""

from gemini.modules.exchangers import HeatExchanger
from gemini.modules.grids import CoolingGrid
from gemini.modules.piping import Valve
from gemini.modules.plant import Plant
from gemini.modules.pumps import CirculationPump
from gemini.types import Inlet, Outlet, Power, Stream


class CoolingSubstation(Plant):
    """Indirect district-cooling substation serving a building chilled-water circuit.

    The network chilled water passes the control ``valve`` and the cold side of the
    ``heat_exchanger``; the building circuit, a closed loop inside the substation, passes its
    hot side, the ``consumer`` (a ``CoolingGrid`` with the building's sensible and latent loads
    and indoor air) and the ``pump``, which sets its flow and its pressure and draws the
    electricity for it through ``power_in``. This is the indirect energy-transfer-station
    connection of district cooling customers (ASHRAE 2013, *District Cooling Guide*, consumer
    interconnection).

    The building loop closes within one call: the plant tears it at ``consumer.return_out``,
    starts at the consumer's return limit, the lower of its ``maximum_return_temperature`` and
    ``indoor_temperature``, and never falls below the network temperature after the valve, where
    the exchanger would reverse. The building supply temperature that reaches the consumer
    decides whether it can dehumidify (its dew-point test). That test is on or off, so near the
    threshold the loop can lack a steady state: meeting the latent load warms the supply above
    the threshold and dropping it cools the supply below. The real coil would then dehumidify
    partly; the consumer model cannot, and the loop raises ``PhysicsError`` (code
    ``loop_not_converged``; for the test configuration a band of about 2 K of network
    temperature). Lower the network temperature, raise the building flow or the exchanger UA.

    The valve only throttles: the network flow is imposed by ``supply_in`` and the valve
    reports the pressure drop that flow causes at the commanded ``valve.opening``. Every child
    is first-law closed, so ``energy_balance`` closes; the converged consumer return and the
    stream fed back differ by at most the tolerance and appear as a boundary pair in the audit's
    ``in`` and ``out``.

    Valid in the ranges of the children: liquid circuits, forward flow, a network supply at
    most as warm as the building return.
    """

    def __init__(self):
        """Declare the substation children, its ports and the circuits."""
        super().__init__()

        # Modules
        self.valve = Valve()
        self.heat_exchanger = HeatExchanger()
        self.consumer = CoolingGrid()
        self.pump = CirculationPump()

        # Inlets
        self.supply_in = Inlet(Stream, kind="chilled_water")
        self.power_in = Inlet(Power, kind="electricity")

        # Outlets
        self.return_out = Outlet(Stream, kind="chilled_water")
        self.loss_out = Outlet(Power, kind="heat")

        # Connections
        self.connect("supply_in", "valve.fluid_in")
        self.connect("power_in", "pump.power_in")
        self.connect("valve.fluid_out", "heat_exchanger.cold_in")
        self.connect("heat_exchanger.cold_out", "return_out")
        self.connect("heat_exchanger.hot_out", "consumer.supply_in")
        self.connect("consumer.return_out", "pump.fluid_in")
        self.connect("pump.fluid_out", "heat_exchanger.hot_in")
        self.connect("pump.loss_out", "loss_out")
