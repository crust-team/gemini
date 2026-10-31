"""Nodal doublet with a heat exchanger, a boiler and a CHP on the secondary network."""

from gemini.modules.environment import Atmosphere
from gemini.modules.exchangers import HeatExchanger
from gemini.modules.grids import ElectricityGrid, GasGrid
from gemini.modules.heating import CHP, Boiler
from gemini.modules.module import Module
from gemini.modules.piping import Mixer, Splitter
from gemini.modules.plants.nodaldoublet import NodalDoublet
from gemini.modules.treatment import Degasser, Filter
from gemini.types import Inlet, Outlet, Output, Stream


class BoilerChpPlant(Module):
    """Nodal doublet, surface treatment, exchanger, and a boiler and CHP on the secondary.

    The port of the upstream GEMINI simulator's ``doublet_plant`` example. The producer is solved
    for its rate at the ``doublet.wellhead_pressure`` boundary, the brine passes a degasser, a
    filter, the heat exchanger and a second filter, and the injector is solved for the pump head
    it needs. The secondary water is split in two: one part is heated by the exchanger and topped
    up by a gas boiler, the other is heated by a gas-engine CHP, and both are mixed again.
    ``gm.plants.example`` carries the well, reservoir and ESP data of the upstream example.
    """

    def __init__(self):
        """Build the plant in flow order."""
        super().__init__()

        # Modules
        self.doublet = NodalDoublet()
        self.degasser = Degasser()
        self.hot_filter = Filter()
        self.heat_exchanger = HeatExchanger()
        self.cold_filter = Filter()
        self.splitter = Splitter()
        self.boiler_gas = GasGrid()
        self.chp_gas = GasGrid()
        self.boiler = Boiler()
        self.chp = CHP()
        self.mixer = Mixer()
        self.electricity_grid = ElectricityGrid()
        self.air = Atmosphere()

        # Inlets
        self.return_in = Inlet(Stream)

        # Outputs
        self.production_rate = Output.of(self.doublet.riser.wellhead_out.field("m_dot"))
        self.duty = Output.of(self.heat_exchanger.duty)
        self.injection_pump_power = Output.of(self.doublet.injection_pump.power)
        self.supply_out_T = Output.of(self.mixer.fluid_out.field("T"))

        # Outlets
        self.supply_out = Outlet(Stream)

    def forward(self, inlets):
        """Produce, treat, exchange and inject the brine; heat and remix the secondary water."""

        # Modules
        supply, lift_power, well_losses = self.doublet.produce()
        degassed = self.degasser(fluid_in=supply)
        filtered = self.hot_filter(fluid_in=degassed.outlets.liquid_out)
        split = self.splitter(fluid_in=inlets.return_in)
        exchanged = self.heat_exchanger(
            hot_in=filtered.outlets.fluid_out, cold_in=split.outlets.branch1_out
        )
        returned = self.cold_filter(fluid_in=exchanged.outlets.hot_out)
        injection_power, injection_loss = self.doublet.inject(returned.outlets.fluid_out)
        self.doublet.formation(heat_in=well_losses + injection_loss)
        boiled = self.boiler(
            fluid_in=exchanged.outlets.cold_out, fuel_in=self.boiler_gas.offer()["gas_out"]
        )
        cogenerated = self.chp(
            fluid_in=split.outlets.branch2_out, fuel_in=self.chp_gas.offer()["gas_out"]
        )
        mixed = self.mixer(
            branch1_in=boiled.outlets.fluid_out, branch2_in=cogenerated.outlets.fluid_out
        )
        self.boiler_gas(gas_out=boiled.inlets.fuel_in)
        self.chp_gas(gas_out=cogenerated.inlets.fuel_in)
        self.electricity_grid(
            power_in=[cogenerated.outlets.power_out], power_out=[lift_power, injection_power]
        )
        self.air(
            air_in=[],
            gas_in=[
                degassed.outlets.gas_out,
                boiled.outlets.flue_out,
                cogenerated.outlets.flue_out,
            ],
            heat_in=[boiled.outlets.loss_out, cogenerated.outlets.loss_out],
        )

        # Outlets
        supply_out = mixed.outlets.fluid_out

        outlets = dict(supply_out=supply_out)
        return outlets
