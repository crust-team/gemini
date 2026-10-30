"""Auxiliary gas or electric boiler with a steady first-law heat balance."""

from typing import Literal

from gemini import ops
from gemini.errors import PhysicsError
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
    Outlet,
    Output,
    Parameter,
    Power,
    Stream,
    Temperature,
)


class Boiler(Module):
    """Auxiliary gas or electric boiler with a thermal capacity limit."""

    def __init__(self):
        """Declare boiler design data, ports and computed performance."""
        super().__init__()

        # Parameters
        self.fuel_type = Parameter(Literal["gas", "electric"])
        self.capacity = Parameter(Power, gt=0)
        self.efficiency = Parameter(Efficiency)

        # Inlets
        self.inlet = Inlet(Stream, stream="hot_water")

        # Controls
        self.temperature_setpoint = Control(Temperature)

        # Outputs
        self.duty = Output(Duty)
        self.fuel_or_power = Output(Power)
        self.outlet_T = Output(Temperature)
        self.is_capped = Output(bool)
        self.electricity = Output(Electricity)
        self.fuel = Output(Fuel)
        self.heat_loss = Output(HeatLoss)

        # Outlets
        self.outlet = Outlet(Stream, stream="hot_water")

    def forward(self, inlets):
        """Heat a forward stream up to its setpoint, conserving energy."""

        # Outlets
        inlet = inlets.inlet
        ops.check(
            inlet.m_dot >= 0,
            PhysicsError,
            "{path}: inlet.m_dot = {m_dot} kg/s; expected >= 0",
            path=self.path,
            m_dot=inlet.m_dot,
        )
        rate = inlet.heat_capacity_rate()
        requested = heat_transfer.setpoint_duty(rate, self.temperature_setpoint - inlet.T)
        duty = ops.minimum(requested, self.capacity)
        outlet_T = inlet.T + heat_transfer.temperature_change(duty, rate)

        outlet = inlet.with_(T=outlet_T)

        outlets = dict(outlet=outlet)
        return outlets

    def _compute_outputs(self, inlets, outlets):
        inlet = inlets.inlet
        outlet = outlets.outlet
        requested = heat_transfer.setpoint_duty(
            inlet.heat_capacity_rate(), self.temperature_setpoint - inlet.T
        )
        self.duty = ops.minimum(requested, self.capacity)
        self.fuel_or_power = energy.input_power(self.duty, self.efficiency)
        self.outlet_T = outlet.T
        self.is_capped = requested > self.capacity
        self.electricity = self.fuel_or_power if self.fuel_type == "electric" else 0
        self.fuel = self.fuel_or_power if self.fuel_type == "gas" else 0
        self.heat_loss = self.fuel_or_power - self.duty
