"""Doublet with a nodal-solved production rate and a boiler and CHP on the secondary network.

The port of the upstream GEMINI simulator's ``doublet_plant`` example. The producer is solved
for its rate at a 3 bar wellhead pressure (nodal analysis), the brine passes a degasser, a
filter, the heat exchanger and a second filter, and the injector is solved for the pump head it
needs: its 3100 m column already over-delivers, so no pump is needed and the injection pump
draws nothing. On the secondary side 140 m3/h of 20 degC water is split in two: one half is
heated by the exchanger and topped up by a gas boiler, the other is heated by a gas-engine CHP,
and both are mixed again.

Well, reservoir and ESP data are the upstream example's. The upstream boiler and CHP are driven
by a gas flow with a fixed one-third electric share; the refactored ``Boiler`` and ``CHP`` are
driven by a setpoint and a load instead, so their design values below are this example's own.
Emissions use the upstream factors, 56.6 kg CO2/GJ of gas and 0.3 kg CO2/kWh of grid
electricity, through ``emissions``, which nets the CHP's generation against the plant's use.

Run from the repository root:
PYTHONPATH=. python examples/plants/simulate/03_boiler_chp_secondary.py
"""

import gemini as gm
from examples.shared.nodal_doublet import NodalDoublet
from gemini.modules import CHP, Boiler, GasGrid, HeatExchanger, Mixer, Splitter, emissions
from gemini.modules.treatment import Degasser, Filter
from gemini.physics.geometry import build_path
from gemini.types import (
    Electricity,
    ElectricityGenerated,
    Fuel,
    Inlet,
    Outlet,
    Output,
    Stream,
)

GAS_FACTOR = 56.6 / 1e9
"""CO2 emitted per joule of natural gas [kg/J]: 56.6 kg/GJ."""

GRID_FACTOR = 0.3 / 3.6e6
"""CO2 emitted per joule of grid electricity [kg/J]: 0.3 kg/kWh."""

ESP_HEAD = [83.08389282, -0.000460444, -1.19e-07, 1.69e-11, -6.36e-16, 6.69e-21]
ESP_POWER = [10.02089977, -0.000160233, 6.52e-08, -2.13e-12, 1.71e-17, 1.38e-23]
INDEX = 10 / 3.6e8
"""Productivity and injectivity index [m3/s/Pa]: 10 m3/h/bar."""


class BoilerChpPlant(gm.modules.Module):
    """Nodal doublet, surface treatment, exchanger, and a boiler and CHP on the secondary."""

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
        self.grid = GasGrid()
        self.boiler = Boiler()
        self.chp = CHP()
        self.mixer = Mixer()

        # Inlets
        self.return_in = Inlet(Stream)

        # Outputs
        self.production_rate = Output.of(self.doublet.riser.wellhead_out.field("m_dot"))
        self.exchanger_duty = Output.of(self.heat_exchanger.duty)
        self.injection_pump_electricity = Output.of(self.doublet.injection_pump.electricity)
        self.electricity = Output(Electricity)
        self.electricity_generated = Output(ElectricityGenerated)
        self.fuel = Output(Fuel)
        self.secondary_out_T = Output.of(self.mixer.fluid_out_T)

        # Outlets
        self.supply_out = Outlet(Stream)

    def forward(self, inlets):
        """Produce, treat, exchange and inject the brine; heat and remix the secondary water."""

        # Modules
        supply, _ = self.doublet.produce()
        degassed = self.degasser(fluid_in=supply)
        filtered = self.hot_filter(fluid_in=degassed.outlets.liquid_out)
        split = self.splitter(fluid_in=inlets.return_in)
        exchanged = self.heat_exchanger(
            hot_in=filtered.outlets.fluid_out, cold_in=split.outlets.branch1_out
        )
        returned = self.cold_filter(fluid_in=exchanged.outlets.hot_out)
        self.doublet.inject(returned.outlets.fluid_out)
        gas = self.grid().outlets.fluid_out
        boiled = self.boiler(fluid_in=exchanged.outlets.cold_out, fuel_in=gas)
        cogenerated = self.chp(fluid_in=split.outlets.branch2_out, fuel_in=gas)
        mixed = self.mixer(
            branch1_in=boiled.outlets.fluid_out, branch2_in=cogenerated.outlets.fluid_out
        )

        # Outlets
        supply_out = mixed.outlets.fluid_out

        outlets = dict(supply_out=supply_out)
        return outlets


def vertical_path(depth):
    """Return the upstream survey of a vertical 0.15 m bore to ``depth`` [m], 1 cm roughness."""
    stations = (0, 300, 400, 600, depth)
    return build_path([dict(MD=md, TVD=md, ID=0.15, roughness=0.01) for md in stations])


def configure_doublet(doublet):
    """Fill the upstream doublet-A wells: 250 bar producer with an ESP, 240 bar injector."""
    reservoir = dict(
        temperature="80 degC",
        permeability=1e-12,
        aquifer_thickness=100,
        drainage_radius=0,
        wellbore_radius=0.1,
    )
    doublet.reservoir.update_params(
        pressure="250 bar", productivity_index=INDEX, top_depth=2400, **reservoir
    )
    producer = dict(pipe_path=vertical_path(2400), soil_temperature="20 degC", esp_depth=650)
    doublet.well.update_params(segment="below_esp", **producer)
    doublet.riser.update_params(segment="above_esp", **producer)
    doublet.esp.update_params(
        stage_count=10, head_coefficients=ESP_HEAD, power_coefficients=ESP_POWER
    )
    doublet.esp.frequency = "65 Hz"
    doublet.injection_pump.update_params(efficiency=0.8)
    doublet.injector.update_params(pipe_path=vertical_path(3100), soil_temperature="20 degC")
    doublet.sink.update_params(
        pressure="240 bar", injectivity_index=INDEX, top_depth=3100, **reservoir
    )
    doublet.update_params(production_rates=(5, 60), maximum_injection_pressure="500 bar")
    doublet.wellhead_pressure = "3 bar"


def configure_surface(plant):
    """Fill the exchanger, the 50/50 secondary split, the boiler and the CHP."""
    plant.heat_exchanger.update_params(
        thermal_conductance=2.5e5,
        hot_nominal_pressure_drop=0,
        cold_nominal_pressure_drop=0,
        hot_nominal_mass_flow=36,
        cold_nominal_mass_flow=19.4,
    )
    plant.splitter.split_fraction = 0.5
    plant.boiler.update_params(capacity="3 MW", efficiency=0.8)
    plant.boiler.temperature_setpoint = "70 degC"
    plant.chp.update_params(
        electric_capacity="400 kW",
        electric_efficiency=0.4,
        thermal_efficiency=0.45,
        maximum_outlet_temperature="90 degC",
    )
    plant.chp.load_fraction = 1.0


plant = BoilerChpPlant()
configure_doublet(plant.doublet)
configure_surface(plant)
secondary = gm.Stream(flow="140 m3/h", T="20 degC", p="3 bar", fluid=gm.Fluid(kind="water"))
result = plant(return_in=secondary)
out = result.outputs
pump_power = out.injection_pump_electricity
print(f"Primary flow (nodal solve):  {out.production_rate / 1000 * 3600:.2f} m3/h")
print(f"Exchanger duty:              {out.get('exchanger_duty', unit='MW'):.3f} MW")
print(f"Secondary outlet:            {out.get('secondary_out_T', unit='degC'):.2f} degC")
print(f"Gas burnt:                   {out.get('fuel', unit='MW'):.3f} MW")
print(f"CHP electricity:             {out.get('electricity_generated', unit='MW'):.3f} MW")
print(f"Electricity used:            {out.get('electricity', unit='MW'):.3f} MW")
print(f"Injection pump:              {pump_power:.1f} W (no pump needed)")
print(
    f"CO2 emissions:               {emissions(result, GAS_FACTOR, GRID_FACTOR) * 86400:.0f} kg/day"
)
assert pump_power == 0
