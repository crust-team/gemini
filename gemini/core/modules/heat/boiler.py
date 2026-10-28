"""Auxiliary gas or electric boiler with a steady first-law heat balance."""

from typing import Literal

from gemini.core.modules.module import Module
from gemini.core.types import (
    Control,
    Efficiency,
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
        self.inlet = Inlet(Stream)

        # Controls
        self.setpoint_T = Control(Temperature)

        # Outputs
        self.duty = Output(Power)
        self.fuel_or_power = Output(Power)
        self.outlet_T = Output(Temperature)
        self.capped = Output(bool)
        self.electricity = Output(Power)
        self.fuel = Output(Power)
        self.heat_loss = Output(Power)

        # Outlets
        self.outlet = Outlet(Stream)

    def forward(self, inlets):
        """Heat a forward stream up to its setpoint, conserving energy."""

        # Outlets
        inlet = inlets.inlet
        if inlet.m_dot < 0:
            raise ValueError(f"{self.path}: negative mass flow {inlet.m_dot}")
        cp = inlet.fluid.properties(inlet.p, inlet.T).cp_l
        requested = inlet.m_dot * cp * max(0, self.setpoint_T - inlet.T)
        duty = min(requested, self.capacity)
        outlet_T = inlet.T + duty / (inlet.m_dot * cp) if inlet.m_dot else inlet.T

        outlet = inlet.with_(T=outlet_T)

        outlets = dict(outlet=outlet)
        return outlets

    def _compute_outputs(self, inlets, outlets):
        inlet = inlets.inlet
        outlet = outlets.outlet
        cp = inlet.fluid.properties(inlet.p, inlet.T).cp_l
        requested = inlet.m_dot * cp * max(0, self.setpoint_T - inlet.T)
        self.duty = min(requested, self.capacity)
        self.fuel_or_power = self.duty / self.efficiency
        self.outlet_T = outlet.T
        self.capped = requested > self.capacity
        self.electricity = self.fuel_or_power if self.fuel_type == "electric" else 0
        self.fuel = self.fuel_or_power if self.fuel_type == "gas" else 0
        self.heat_loss = self.fuel_or_power - self.duty
