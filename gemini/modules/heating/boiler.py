"""Auxiliary boilers with a steady first-law heat balance: gas-fired and electric."""

from gemini import ops
from gemini.errors import PhysicsError
from gemini.modules._utils import burner
from gemini.modules.module import Module
from gemini.physics import energy, heat_transfer
from gemini.types import (
    Control,
    Duty,
    Efficiency,
    Electricity,
    Fuel,
    HeatLoss,
    Inlet,
    MassFlow,
    Outlet,
    Output,
    Parameter,
    Power,
    Stream,
    Temperature,
)
from gemini.types.cost import scaled_cost


class _BoilerBody(Module):
    """Water side of a boiler: heat a forward stream to its setpoint, up to a duty limit."""

    def __init__(self):
        super().__init__()

        # Parameters
        self.capacity = Parameter(Power, gt=0)
        self.efficiency = Parameter(Efficiency)

        # Inlets
        self.fluid_in = Inlet(Stream, kind="hot_water")

        # Controls
        self.temperature_setpoint = Control(Temperature)

        # Outputs
        self.duty = Output(Duty)
        self.fuel_or_power = Output(Power)
        self.fluid_out_T = Output(Temperature)
        self.is_capped = Output(bool)
        self.heat_loss = Output(HeatLoss)

        # Outlets
        self.fluid_out = Outlet(Stream, kind="hot_water")

    def _requested_duty(self, inlet):
        """Return the duty [W] that reaches the setpoint, refusing reverse flow."""
        ops.check(
            inlet.m_dot >= 0,
            PhysicsError,
            "{path}: fluid_in.m_dot = {m_dot} kg/s; expected >= 0",
            path=self.path,
            m_dot=inlet.m_dot,
        )
        return heat_transfer.setpoint_duty(
            inlet.heat_capacity_rate(), self.temperature_setpoint - inlet.T
        )

    def _heated(self, inlet, duty):
        """Return the inlet stream heated by ``duty``."""
        rate = inlet.heat_capacity_rate()
        return inlet.with_(T=inlet.T + heat_transfer.temperature_change(duty, rate))

    def _water_outputs(self, inlet, outlet, limit):
        """Record the outputs of the water side at the duty limit ``limit`` [W]."""
        requested = self._requested_duty(inlet)
        self.duty = ops.minimum(requested, limit)
        self.fuel_or_power = energy.input_power(self.duty, self.efficiency)
        self.fluid_out_T = outlet.T
        self.is_capped = requested > limit
        self.heat_loss = self.fuel_or_power - self.duty


class Boiler(_BoilerBody):
    """Auxiliary gas boiler with a thermal capacity limit, burning co-produced gas first.

    Each step it needs ``duty / efficiency`` of fuel energy. ``fuel_in`` brings the co-produced gas:
    the boiler burns it first, up to its need, and takes the rest from the grid; the port returns
    what it burned, and a ``GasMakeup`` sends the rest to ``excess_out``. It may draw grid gas when
    ``fuel_in`` comes from a ``GasMakeup`` or a ``GasGrid``, which mark the stream with the grid
    composition; without that mark the fuel energy of the stream limits the duty.

    ``fuel`` is the total, ``fuel_coproduced`` and ``fuel_purchased`` its parts [W],
    ``burned_mass_flow`` the co-produced gas burned [kg/s] and ``co2_emission`` the CO2 of
    everything burned, formed and carried in the gas [kg/s]. Purchased gas enters no stream: its
    mass is not in ``mass_balance``, and its chemical energy is the ``fuel`` input of
    ``energy_balance``.
    """

    def __init__(self):
        """Declare boiler design data, ports and computed performance."""
        super().__init__()

        # Inlets
        self.fuel_in = Inlet(Stream, kind="gas", drawn=True)

        # Outputs
        self.fuel = Output(Fuel)
        self.fuel_coproduced = Output(Fuel)
        self.fuel_purchased = Output(Fuel)
        self.burned_mass_flow = Output(MassFlow)
        self.co2_emission = Output(MassFlow)

    def forward(self, inlets):
        """Heat the stream up to its setpoint and return the gas it burned."""

        # Outlets
        inlet, fuel = inlets.fluid_in, inlets.fuel_in
        duty = ops.minimum(self._requested_duty(inlet), self._duty_limit(fuel))
        outlet = self._heated(inlet, duty)
        fuel_in = burner.burned_stream(energy.input_power(duty, self.efficiency), fuel)

        outlets = dict(fluid_out=outlet, fuel_in=fuel_in)
        return outlets

    def _compute_outputs(self, inlets, outlets):
        fuel = inlets.fuel_in
        self._water_outputs(inlets.fluid_in, outlets.fluid_out, self._duty_limit(fuel))
        self.fuel = self.fuel_or_power
        for name, value in burner.fuel_outputs(self.fuel_or_power, fuel).items():
            setattr(self, name, value)

    def capex(self, assumptions):
        """Return the cost of the boiler from its capacity."""
        return scaled_cost(assumptions, "boiler_cost", self.capacity)

    def _duty_limit(self, fuel):
        """Return the capacity, or less when the stream alone must cover the fuel [W]."""
        if burner.has_grid(fuel):
            return self.capacity
        useful = energy.output_power(burner.available_fuel(fuel), self.efficiency)
        return ops.minimum(self.capacity, useful)


class ElectricBoiler(_BoilerBody):
    """Auxiliary electric boiler with a thermal capacity limit; it has no gas ports."""

    def __init__(self):
        """Declare boiler design data, ports and computed performance."""
        super().__init__()

        # Inlets
        self.power_in = Inlet(Power, kind="electricity")

        # Outputs
        self.electricity = Output(Electricity)

    def forward(self, inlets):
        """Heat the stream up to its setpoint."""

        # Outlets
        inlet = inlets.fluid_in
        duty = ops.minimum(self._requested_duty(inlet), self.capacity)
        outlet = self._heated(inlet, duty)

        outlets = dict(fluid_out=outlet, power_in=energy.input_power(duty, self.efficiency))
        return outlets

    def _compute_outputs(self, inlets, outlets):
        self._water_outputs(inlets.fluid_in, outlets.fluid_out, self.capacity)
        self.electricity = self.fuel_or_power
