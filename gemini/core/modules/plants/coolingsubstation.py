"""Building cooling substation: network valve, heat exchanger and the building's cooling loads."""

from gemini.core.modules.demand import CoolingConsumer
from gemini.core.modules.heat import HeatExchanger
from gemini.core.modules.module import Module
from gemini.core.modules.piping import Valve
from gemini.core.modules.plants import loops
from gemini.core.types import (
    HeatAbsorbed,
    Inlet,
    MassFlow,
    Outlet,
    Output,
    Parameter,
    Pressure,
    Stream,
)


class CoolingSubstation(Module):
    """Indirect district-cooling substation serving a building chilled-water circuit.

    The network chilled water passes the control ``valve`` and the cold side of the
    ``heat_exchanger``; the building circuit, a closed loop inside the substation, passes its
    hot side and the ``consumer`` (a ``CoolingConsumer`` with the building's sensible and latent
    loads and indoor air). The building circuit carries the parameter ``building_flow`` at
    ``building_pressure`` with the substation's ``fluid``; its circulation pump and hydraulics
    are not modelled. This is the indirect energy-transfer-station connection of district
    cooling customers (ASHRAE 2013, *District Cooling Guide*, consumer interconnection).

    The building return temperature closes the loop within one call: ``loops.close_loop`` finds
    the return temperature that one pass through exchanger and consumer reproduces (Wegstein
    iteration, tolerance 1e-9 K, at most 50 passes, ``PhysicsRangeError`` otherwise), with
    trial passes evaluated by ``Module.trial_outlets``; then every child is called once. The
    iteration starts at the consumer's return limit, the lower of its
    ``maximum_return_temperature`` and ``indoor_temperature`` (or the network temperature, if
    warmer), and never falls below the network temperature after the valve, where the exchanger
    would reverse. A stopped network or building circuit transfers no heat. The building supply
    temperature that reaches the consumer decides whether it can dehumidify (its dew-point test).
    That test is on or off, so near the threshold the loop can lack a steady state: meeting the
    latent load warms the supply above the threshold and dropping it cools the supply below.
    The real coil would then dehumidify partly; the consumer model cannot, and the iteration
    raises ``PhysicsRangeError`` (for the test configuration a band of about 2 K of network
    temperature). Lower the network temperature, raise the building flow or the exchanger UA.

    The valve only throttles: the network flow is imposed by ``network_in`` and the valve
    reports the pressure drop that flow causes at the commanded ``valve.opening``. Every child
    is first-law closed, so ``energy_balance`` closes; the converged consumer return and the
    stream fed back to the exchanger differ by at most the tolerance and appear as a boundary
    pair in the audit's ``in`` and ``out``.

    Valid in the ranges of the children: liquid circuits, forward flow, a network supply at
    most as warm as the building return.
    """

    category = "plant"

    def __init__(self):
        """Declare the substation children, the building circuit and the absorbed heat."""
        super().__init__()

        # Modules
        self.valve = Valve()
        self.heat_exchanger = HeatExchanger()
        self.consumer = CoolingConsumer()

        # Parameters
        self.building_flow = Parameter(MassFlow, gt=0)
        self.building_pressure = Parameter(Pressure, gt=0)

        # Inlets
        self.network_in = Inlet(Stream, stream="chilled_water")

        # Outputs
        self.duty = Output.of(self.heat_exchanger.duty)
        self.heat_absorbed = Output(HeatAbsorbed)
        self.unmet_sensible = Output.of(self.consumer.unmet_sensible)
        self.unmet_latent = Output.of(self.consumer.unmet_latent)
        self.is_unmet = Output.of(self.consumer.is_unmet)
        self.dew_point = Output.of(self.consumer.dew_point)
        self.building_supply_T = Output.of(self.heat_exchanger.hot_out_T)
        self.building_return_T = Output.of(self.consumer.return_out_T)
        self.network_out_T = Output.of(self.heat_exchanger.cold_out_T)
        self.valve_pressure_drop = Output.of(self.valve.pressure_drop)

        # Outlets
        self.network_out = Outlet(Stream, stream="chilled_water")

    def forward(self, inlets):
        """Throttle the network water, close the building loop and exchange the heat once."""

        # Modules
        throttled = self.valve(inlet=inlets.network_in)
        network = throttled.outlets.outlet
        consumer = self.consumer
        limit = min(consumer.maximum_return_temperature, consumer.indoor_temperature)
        return_T = loops.close_loop(
            lambda temperature: self._pass(network, temperature),
            max(limit, network.T),
            self.path,
            lower=network.T,
        )
        exchanged = self.heat_exchanger(hot_in=self._building_return(return_T), cold_in=network)
        self.consumer(supply_in=exchanged.outlets.hot_out)

        # Outlets
        network_out = exchanged.outlets.cold_out

        outlets = dict(network_out=network_out)
        return outlets

    def _pass(self, network, return_T):
        """Return the building return temperature [K] after one trial pass around the loop."""
        building = self._building_return(return_T)
        exchanged = self.heat_exchanger.trial_outlets({"hot_in": building, "cold_in": network})
        consumed = self.consumer.trial_outlets({"supply_in": exchanged.hot_out})
        return consumed.return_out.T

    def _building_return(self, temperature):
        """Return the building circuit stream entering the exchanger at ``temperature`` [K]."""
        return Stream(
            m_dot=self.building_flow, T=temperature, p=self.building_pressure, fluid=self.fluid
        )
