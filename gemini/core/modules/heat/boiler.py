"""Auxiliary gas or electric boiler with a steady first-law heat balance."""

from typing import Literal

from gemini.core.modules.module import Module
from gemini.core.types import (
    Control,
    Efficiency,
    FuelFlow,
    HeatFlow,
    Inlet,
    Outlet,
    Output,
    Parameter,
    Power,
    PowerFlow,
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

        # Outlets
        self.outlet = Outlet(Stream)
        self.electricity = Outlet(PowerFlow)
        self.fuel = Outlet(FuelFlow)
        self.heat_loss = Outlet(HeatFlow)

    def forward(self, inlet, setpoint_T):
        """Heat a forward stream up to its setpoint, conserving energy."""

        # Outputs
        if inlet.m_dot < 0:
            raise ValueError(f"{self.path}: negative mass flow {inlet.m_dot}")
        cp = inlet.fluid.properties(inlet.p, inlet.T).cp_l
        requested = inlet.m_dot * cp * max(0, setpoint_T - inlet.T)
        self.duty = min(requested, self.capacity)
        self.fuel_or_power = self.duty / self.efficiency
        self.outlet_T = inlet.T + self.duty / (inlet.m_dot * cp) if inlet.m_dot else inlet.T
        self.capped = requested > self.capacity

        # Outlets
        outlet = inlet.with_(T=self.outlet_T)
        electricity = PowerFlow(P=self.fuel_or_power if self.fuel_type == "electric" else 0)
        fuel = FuelFlow(P=self.fuel_or_power if self.fuel_type == "gas" else 0)
        heat_loss = HeatFlow(Q=self.fuel_or_power - self.duty)

        outlets = dict(
            outlet=outlet,
            electricity=electricity,
            fuel=fuel,
            heat_loss=heat_loss,
        )
        return outlets
