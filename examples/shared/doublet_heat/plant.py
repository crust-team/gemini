"""Example doublet heat plant with every connection written explicitly."""

from gemini.core.modules import Module, ModuleDict
from gemini.core.modules.heat import HeatExchanger
from gemini.core.modules.plants import Doublet
from gemini.core.modules.pumps import InjectionPump
from gemini.core.modules.treatment import Degasser, Filter
from gemini.core.types import (
    Control,
    Frequency,
    HeatFlow,
    Inlet,
    MassFlow,
    Outlet,
    Output,
    Power,
    PowerFlow,
    Pressure,
    Ratio,
    Stream,
)


class DoubletHeatPlant(Module):
    """Doublet, degasser, filters, heat exchanger and injection pump in diagram order."""

    def __init__(self):
        """Declare the complete plant tree, ports, controls and outputs."""
        super().__init__()

        # Modules
        self.doublet = Doublet()
        self.degasser = Degasser()
        self.filters = ModuleDict({"hot": Filter(), "cold": Filter()})
        self.heat_exchanger = HeatExchanger()
        self.injection_pump = InjectionPump()

        # Inlets
        self.secondary = Inlet(Stream)

        # Controls
        self.m_dot = Control(MassFlow)
        self.esp_frequency = Control(Frequency)
        self.injection_pressure = Control(Pressure)
        self.injection_frequency = Control(Frequency, default=60)

        # Outputs
        self.thermal_power = Output(Power)
        self.electricity_use = Output(Power)
        self.cop = Output(Ratio | None, optional=True)

        # Outlets
        self.secondary_out = Outlet(Stream)
        self.gas = Outlet(Stream)
        self.electricity = Outlet(PowerFlow)
        self.heat_loss = Outlet(HeatFlow)

    def forward(self, secondary, m_dot, esp_frequency, injection_pressure, injection_frequency):
        """Connect the doublet limbs through the modeled surface equipment."""

        # Modules
        supply, esp_power, production_heat = self.doublet.produce(m_dot, esp_frequency)
        degassed = self.degasser(inlet=supply)
        filtered = self.filters.hot(inlet=degassed.outlets.liquid)
        exchanged = self.heat_exchanger(hot_in=filtered.outlets.outlet, cold_in=secondary)
        returned = self.filters.cold(inlet=exchanged.outlets.hot_out)
        pumped = self.injection_pump(
            suction=returned.outlets.outlet,
            pressure_setpoint=injection_pressure,
            frequency=injection_frequency,
        )
        injection_heat = self.doublet.inject(pumped.outlets.discharge)

        # Outputs
        self.electricity_use = esp_power.P + pumped.outlets.electricity.P
        self.thermal_power = exchanged.outputs.duty
        self.cop = self.thermal_power / self.electricity_use if self.electricity_use else None

        # Outlets
        secondary_out = exchanged.outlets.cold_out
        gas = degassed.outlets.gas
        electricity = PowerFlow(P=self.electricity_use)
        heat_loss = HeatFlow(Q=production_heat.Q + injection_heat.Q)

        outlets = dict(
            secondary_out=secondary_out,
            gas=gas,
            electricity=electricity,
            heat_loss=heat_loss,
        )
        return outlets
