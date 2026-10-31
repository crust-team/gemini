"""Space or process heat demand on a hydronic circuit with a steady first-law balance."""

from gemini import ops
from gemini.errors import PhysicsError
from gemini.modules.module import Module
from gemini.physics import heat_transfer
from gemini.types import (
    Boundary,
    HeatSupplied,
    Inlet,
    Outlet,
    Output,
    Parameter,
    Power,
    Stream,
    Temperature,
    TemperatureDifference,
)


class HeatConsumer(Module):
    """Heat consumer that cools the supply stream by the delivered heat demand.

    The circuit's mass flow is imposed by the supply stream (the consumer has no flow control),
    so the return temperature follows from the delivered heat:

    Q_available = m_dot cp max(0, T_supply - T_return,min)
    Q = min(heat_demand, Q_available)
    T_return = T_supply - Q / (m_dot cp)

    The return temperature is floored at ``minimum_return_temperature``, the lowest
    temperature the consumer's emitters or process heat exchanger can cool the water to (for
    example the space temperature plus an emitter approach, or a legionella or process limit).
    Demand beyond ``Q_available`` is ``unmet_demand``. A supply colder than the minimum return
    temperature delivers nothing and returns unchanged; the consumer never heats the water.

    Simplifications: steady state without circuit inventory, constant fluid properties (the
    inlet ``cp``), no pressure drop (pipes and valves carry the hydraulics) and no emitter
    characteristic: whether the emitters can actually transfer ``heat_demand`` at the given
    temperatures is the caller's assumption, bounded only by the return floor. There is no
    design return temperature parameter, because with an imposed flow it would not change the
    result. Mass is conserved and the model is first-law closed: the sensible enthalpy drop of
    the stream equals ``heat_supplied``. Valid for liquid water, brine or glycol circuits at any
    temperature above freezing, with nonnegative flow.

    Reference: the steady hydronic heat balance Q = m_dot cp (T_supply - T_return), ASHRAE
    Handbook - HVAC Systems and Equipment (2020), chapter 13, "Hydronic heating and cooling".
    """

    def __init__(self):
        """Declare the consumer's return limit, demand boundary and delivered heat."""
        super().__init__()

        # Parameters
        self.minimum_return_temperature = Parameter(Temperature)

        # Inlets
        self.supply_in = Inlet(Stream, stream="hot_water")

        # Boundaries
        self.heat_demand = Boundary(Power, ge=0)

        # Outputs
        self.supply_in_T = Output(Temperature)
        self.heat_supplied = Output(HeatSupplied)
        self.unmet_demand = Output(Power)
        self.return_out_T = Output(Temperature)
        self.temperature_difference = Output(TemperatureDifference)
        self.is_unmet = Output(bool)

        # Outlets
        self.return_out = Outlet(Stream, stream="hot_water")

    def forward(self, inlets):
        """Return the supply stream cooled by the delivered heat."""

        # Outlets
        supply_in = inlets.supply_in
        delivered = self._delivered_heat(supply_in)
        capacity_rate = supply_in.heat_capacity_rate()
        cooled = ops.maximum(
            self.minimum_return_temperature,
            supply_in.T - heat_transfer.temperature_change(delivered, capacity_rate),
        )
        return_T = ops.where(delivered == 0, supply_in.T, cooled)
        return_out = supply_in.with_(T=return_T)

        outlets = dict(return_out=return_out)
        return outlets

    def _compute_outputs(self, inlets, outlets):
        supply_in = inlets.supply_in
        return_out = outlets.return_out
        self.supply_in_T = supply_in.T
        self.heat_supplied = self._delivered_heat(supply_in)
        self.unmet_demand = self.heat_demand - self.heat_supplied
        self.return_out_T = return_out.T
        self.temperature_difference = supply_in.T - return_out.T
        self.is_unmet = self.unmet_demand > 0

    def _delivered_heat(self, supply_in):
        """Return the delivered heat [W]: the demand, capped by the return-temperature floor."""
        ops.check(
            supply_in.m_dot >= 0,
            PhysicsError,
            "{path}: supply_in.m_dot = {m_dot} kg/s; expected >= 0",
            path=self.path,
            m_dot=supply_in.m_dot,
        )
        available = heat_transfer.setpoint_duty(
            supply_in.heat_capacity_rate(), supply_in.T - self.minimum_return_temperature
        )
        return ops.minimum(self.heat_demand, available)
