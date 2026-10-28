"""Reusable production and reinjection limbs of a geothermal doublet."""

from gemini.core.modules.module import Module
from gemini.core.modules.pumps import ESP
from gemini.core.modules.subsurface import (
    InjectionReservoir,
    InjectionWell,
    ProductionReservoir,
    ProductionWell,
)
from gemini.core.types import (
    Control,
    Frequency,
    HeatFlow,
    Inlet,
    MassFlow,
    Outlet,
    PowerFlow,
    Stream,
)


class Doublet(Module):
    """Produce hot supply and return cooled brine to the receiving aquifer."""

    def __init__(self):
        """Build the production-to-injection doublet in flow order."""
        super().__init__()

        # Modules
        self.reservoir = ProductionReservoir()
        self.well = ProductionWell()
        self.esp = ESP()
        self.riser = ProductionWell()
        self.injector = InjectionWell()
        self.sink = InjectionReservoir()

        # Inlets
        self.return_stream = Inlet(Stream)

        # Controls
        self.m_dot = Control(MassFlow, ge=0)
        self.esp_frequency = Control(Frequency)

        # Outlets
        self.supply = Outlet(Stream)
        self.electricity = Outlet(PowerFlow)
        self.heat_loss = Outlet(HeatFlow)

    def produce(self, m_dot, esp_frequency):
        """Traverse reservoir, lower well, ESP and riser."""
        source = self.reservoir(m_dot=m_dot)
        lower = self.well(bottom=source.outlets.sandface)
        pump = self.esp(suction=lower.outlets.wellhead, frequency=esp_frequency)
        upper = self.riser(bottom=pump.outlets.discharge)
        return (
            upper.outlets.wellhead,
            pump.outlets.electricity,
            HeatFlow(Q=lower.outlets.heat_loss.Q + upper.outlets.heat_loss.Q),
        )

    def inject(self, stream):
        """Traverse the injection well and receiving aquifer."""
        injection = self.injector(wellhead=stream)
        self.sink(sandface=injection.outlets.bottom)
        return injection.outlets.heat_loss

    def forward(self, return_stream, m_dot, esp_frequency):
        """Evaluate both limbs for an independently specified return boundary."""

        # Modules
        produced_supply, produced_electricity, produced_heat = self.produce(m_dot, esp_frequency)
        injection_heat = self.inject(return_stream)

        # Outlets
        supply = produced_supply
        electricity = produced_electricity
        heat_loss = HeatFlow(Q=produced_heat.Q + injection_heat.Q)

        outlets = dict(supply=supply, electricity=electricity, heat_loss=heat_loss)
        return outlets
