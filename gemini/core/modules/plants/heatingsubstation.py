"""Building heating substation: network valve, heat exchanger and the building's heat demand."""

from gemini.core.modules.demand import HeatConsumer
from gemini.core.modules.exchangers import HeatExchanger
from gemini.core.modules.module import Module
from gemini.core.modules.piping import Valve
from gemini.core.modules.plants import loops
from gemini.core.types import (
    HeatSupplied,
    Inlet,
    MassFlow,
    Outlet,
    Output,
    Parameter,
    Pressure,
    Stream,
)


class HeatingSubstation(Module):
    """Indirect district-heating substation serving a building heating circuit.

    The network water passes the control ``valve`` and the hot side of the ``heat_exchanger``;
    the building circuit, a closed loop inside the substation, passes its cold side and the
    ``consumer`` (a ``HeatConsumer`` with the building's ``heat_demand``). The building circuit
    carries the parameter ``building_flow`` at ``building_pressure`` with the substation's
    ``fluid``; its circulation pump and hydraulics are not modelled (their electricity is
    outside the network audit). This is the common indirect connection of district heating
    customers (Frederiksen and Werner 2013, *District Heating and Cooling*, Studentlitteratur).

    The building return temperature closes the loop within one call: ``loops.close_loop`` finds
    the return temperature that one pass through exchanger and consumer reproduces (Wegstein
    iteration, tolerance 1e-9 K, at most 50 passes, ``PhysicsRangeError`` otherwise), with
    trial passes evaluated by ``Module.trial_outlets``; then every child is called once. The
    iteration starts at the consumer's ``minimum_return_temperature`` (or the network
    temperature, if colder) and never exceeds the network temperature after the valve, where
    the exchanger would reverse. A stopped network or building circuit transfers no heat.

    The valve only throttles: the network flow is imposed by ``network_in`` (in a
    ``DistrictNetwork`` by its splitters), and the valve reports the pressure drop that flow
    causes at the commanded ``valve.opening``. Every child is first-law closed and the building
    loop passes the same mass flow, so ``energy_balance`` closes; the converged loop still
    differs by at most the tolerance between the consumer's return and the stream fed back to
    the exchanger, which therefore appear as a boundary pair in the audit's ``in`` and ``out``.

    Valid in the ranges of the children: liquid circuits, forward flow, a network supply at
    least as warm as the building return.
    """

    category = "plant"

    def __init__(self):
        """Declare the substation children, the building circuit and the delivered heat."""
        super().__init__()

        # Modules
        self.valve = Valve()
        self.heat_exchanger = HeatExchanger()
        self.consumer = HeatConsumer()

        # Parameters
        self.building_flow = Parameter(MassFlow, gt=0)
        self.building_pressure = Parameter(Pressure, gt=0)

        # Inlets
        self.network_in = Inlet(Stream, stream="hot_water")

        # Outputs
        self.duty = Output.of(self.heat_exchanger.duty)
        self.heat_supplied = Output(HeatSupplied)
        self.unmet_demand = Output.of(self.consumer.unmet_demand)
        self.is_unmet = Output.of(self.consumer.is_unmet)
        self.building_supply_T = Output.of(self.heat_exchanger.cold_out_T)
        self.building_return_T = Output.of(self.consumer.return_out_T)
        self.network_out_T = Output.of(self.heat_exchanger.hot_out_T)
        self.valve_pressure_drop = Output.of(self.valve.pressure_drop)

        # Outlets
        self.network_out = Outlet(Stream, stream="hot_water")

    def forward(self, inlets):
        """Throttle the network water, close the building loop and exchange the heat once."""

        # Modules
        throttled = self.valve(inlet=inlets.network_in)
        network = throttled.outlets.outlet
        start = min(self.consumer.minimum_return_temperature, network.T)
        return_T = loops.close_loop(
            lambda temperature: self._pass(network, temperature),
            start,
            self.path,
            upper=network.T,
        )
        exchanged = self.heat_exchanger(hot_in=network, cold_in=self._building_return(return_T))
        self.consumer(supply_in=exchanged.outlets.cold_out)

        # Outlets
        network_out = exchanged.outlets.hot_out

        outlets = dict(network_out=network_out)
        return outlets

    def _pass(self, network, return_T):
        """Return the building return temperature [K] after one trial pass around the loop."""
        building = self._building_return(return_T)
        exchanged = self.heat_exchanger.trial_outlets({"hot_in": network, "cold_in": building})
        consumed = self.consumer.trial_outlets({"supply_in": exchanged.cold_out})
        return consumed.return_out.T

    def _building_return(self, temperature):
        """Return the building circuit stream entering the exchanger at ``temperature`` [K]."""
        return Stream(
            m_dot=self.building_flow, T=temperature, p=self.building_pressure, fluid=self.fluid
        )
