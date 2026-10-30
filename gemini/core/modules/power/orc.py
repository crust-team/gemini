"""Binary organic Rankine cycle plant driven by geothermal brine, with an air-cooled condenser."""

from gemini import ops
from gemini.core.modules.module import Module
from gemini.core.types import (
    Boundary,
    Efficiency,
    ElectricityGenerated,
    Fraction,
    HeatLoss,
    Inlet,
    Outlet,
    Output,
    Parameter,
    Power,
    Stream,
    Temperature,
    TemperatureDifference,
)
from gemini.errors import PhysicsRangeError


class ORC(Module):
    """Binary ORC plant: the brine heats the cycle, an air-cooled condenser rejects the rest.

    The working fluid condenses at T_c = ambient_temperature + condenser_approach. At design
    the brine is cooled to T_out = max(minimum_brine_outlet_temperature, T_c + pinch); the
    second term keeps the preheater pinch above the condensate. The working fluid sees the
    brine ``pinch`` colder, between T_a = T_in - pinch and T_b = T_out - pinch, so the
    reversible (Lorenz, triangular-cycle) work of the heat input Q = m cp (T_in - T_out) is
    W_rev = m cp ((T_a - T_b) - T_c ln(T_a / T_b)), that is Q (1 - T_c / T_lm) with the
    logarithmic mean T_lm of T_a and T_b. The gross power is ``fraction_of_carnot`` W_rev
    (DiPippo, R. (2007), Ideal thermal efficiency for geothermal binary plants, Geothermics
    36, 276-285; DiPippo, R. (2016), Geothermal Power Plants, 4th ed., chapter 8).
    ``fraction_of_carnot`` is plant specific: second-law efficiencies of operating binary
    plants are roughly 0.3 to 0.6 (DiPippo, R. (2004), Second Law assessment of binary plants
    generating power from low-temperature geothermal fluids, Geothermics 33, 565-586).

    When the gross power would exceed ``capacity``, part of the brine bypasses the plant: the
    processed share is capacity / uncapped gross power and ``brine_out`` is the adiabatic mix
    of bypassed and cooled brine. The cycle efficiency is unchanged at part load (part-load
    degradation is not modelled). An inlet no hotter than T_out produces nothing and leaves
    unchanged.

    The parasitic loads (feed pump, condenser fans, controls) take ``parasitic_fraction`` of the
    gross power and are supplied from it, so ``electricity_generated`` is the net power and
    ``parasitic_power`` is reported separately, not as ``electricity`` (which would count it
    twice in plant totals). The parasitic power ends as heat in the air: ``heat_loss`` is the
    condenser duty plus the parasitic power. First law: heat_input = gross_power +
    condenser_duty and heat_input = electricity_generated + heat_loss, so ``energy_balance``
    closes with the brine's constant ``cp_l``. ``thermal_efficiency`` is net power over heat
    input (DiPippo 2016), ``None`` without heat input. Valid for a single-phase liquid brine.
    """

    def __init__(self):
        """Declare ORC design data, brine ports, ambient boundary and computed performance."""
        super().__init__()

        # Parameters
        self.minimum_brine_outlet_temperature = Parameter(Temperature)
        self.pinch = Parameter(TemperatureDifference, ge=0)
        self.fraction_of_carnot = Parameter(Efficiency)
        self.condenser_approach = Parameter(TemperatureDifference, ge=0)
        self.parasitic_fraction = Parameter(Fraction, lt=1)
        self.capacity = Parameter(Power, gt=0)

        # Inlets
        self.brine_in = Inlet(Stream)

        # Boundaries
        self.ambient_temperature = Boundary(Temperature)

        # Outputs
        self.heat_input = Output(Power)
        self.gross_power = Output(Power)
        self.parasitic_power = Output(Power)
        self.electricity_generated = Output(ElectricityGenerated)
        self.condenser_duty = Output(Power)
        self.heat_loss = Output(HeatLoss)
        self.thermal_efficiency = Output(Fraction | None)
        self.condensing_temperature = Output(Temperature)
        self.brine_out_T = Output(Temperature)
        self.is_capped = Output(bool)

        # Outlets
        self.brine_out = Outlet(Stream)

    def forward(self, inlets):
        """Cool the brine by the heat the cycle takes at the operating point."""

        # Outlets
        brine_in = inlets.brine_in
        design = self._design(brine_in)
        brine_out_T = brine_in.T - design["share"] * (brine_in.T - design["outlet_T"])

        brine_out = brine_in.with_(T=brine_out_T)

        outlets = dict(brine_out=brine_out)
        return outlets

    def _compute_outputs(self, inlets, outlets):
        brine_in = inlets.brine_in
        brine_out = outlets.brine_out
        design = self._design(brine_in)
        cp = brine_in.fluid.properties(brine_in.p, brine_in.T).cp_l
        self.heat_input = brine_in.m_dot * cp * (brine_in.T - brine_out.T)
        self.gross_power = design["cycle_efficiency"] * self.heat_input
        self.parasitic_power = self.parasitic_fraction * self.gross_power
        self.electricity_generated = self.gross_power - self.parasitic_power
        self.condenser_duty = self.heat_input - self.gross_power
        self.heat_loss = self.condenser_duty + self.parasitic_power
        self.thermal_efficiency = ops.where(
            self.heat_input > 0, ops.truediv(self.electricity_generated, self.heat_input), None
        )
        self.condensing_temperature = design["condensing_T"]
        self.brine_out_T = brine_out.T
        self.is_capped = design["is_capped"]

    def _design(self, brine_in):
        """Return the cycle temperatures, gross cycle efficiency and processed brine share."""
        ops.check(
            brine_in.m_dot >= 0,
            PhysicsRangeError,
            "{path}: brine_in.m_dot = {m_dot} kg/s; expected >= 0",
            path=self.path,
            m_dot=brine_in.m_dot,
        )
        condensing_T = self.ambient_temperature + self.condenser_approach
        outlet_T = ops.maximum(self.minimum_brine_outlet_temperature, condensing_T + self.pinch)
        running = brine_in.T > outlet_T
        hot, cold = brine_in.T - self.pinch, outlet_T - self.pinch
        reversible = 1 - ops.truediv(condensing_T * ops.log(ops.truediv(hot, cold)), hot - cold)
        efficiency = self.fraction_of_carnot * reversible
        cp = brine_in.fluid.properties(brine_in.p, brine_in.T).cp_l
        uncapped = efficiency * brine_in.m_dot * cp * (brine_in.T - outlet_T)
        is_capped = uncapped > self.capacity
        share = ops.where(is_capped, ops.truediv(self.capacity, uncapped), 1.0)
        return dict(
            condensing_T=condensing_T,
            outlet_T=outlet_T,
            cycle_efficiency=ops.where(running, efficiency, 0.0),
            share=ops.where(running, share, 0.0),
            is_capped=ops.where(running, is_capped, False),
        )
