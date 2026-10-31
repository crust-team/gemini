"""The hackathon plant: two doublets, heat pump, boiler, absorption cooling, every edge."""

from gemini.modules.cooling import AbsorptionUnit
from gemini.modules.environment import Atmosphere
from gemini.modules.exchangers import Cooler, HeatExchanger
from gemini.modules.grids import (
    ChemicalGrid,
    CoolingGrid,
    ElectricityGrid,
    GasGrid,
    HeatingGrid,
    WasteGrid,
)
from gemini.modules.heating import Boiler, HeatPump
from gemini.modules.piping import GasMakeup, Mixer, Splitter
from gemini.modules.plant import Plant
from gemini.modules.plants.doublet import Doublet
from gemini.modules.treatment import Degasser, Desander, Flare, InhibitorDosing


class HackathonPlant(Plant):
    """The hackathon plant: two doublets, heat pump, boiler, absorption cooling, every edge."""

    def __init__(self):
        """Declare the modules, ports and connections."""
        super().__init__()

        # Modules
        self.d0 = Doublet()
        self.d1 = Doublet()
        self.production = Mixer()
        self.degasser = Degasser()
        self.desander = Desander()
        self.dosing = InhibitorDosing()
        self.waste = WasteGrid()
        self.chemicals = ChemicalGrid()
        self.hx = HeatExchanger()
        self.injection = Splitter()
        self.gas_grid = GasGrid()
        self.makeup = GasMakeup()
        self.boiler = Boiler()
        self.flare = Flare()
        self.grid = ElectricityGrid()
        self.air = Atmosphere()
        self.chiller_cooler = Cooler()
        self.heat_pump = HeatPump()
        self.loads = Splitter()
        self.heat_return = Mixer()
        self.heat_users = HeatingGrid()
        self.chiller = AbsorptionUnit()
        self.cool_users = CoolingGrid()

        # Connections
        self.connect("d0.supply_out", "production.branch1_in")
        self.connect("d1.supply_out", "production.branch2_in")
        self.connect("production.fluid_out", "degasser.fluid_in")
        self.connect("degasser.liquid_out", "desander.fluid_in")
        self.connect("desander.fluid_out", "dosing.fluid_in")
        self.connect("desander.waste_out", "waste.waste_in")
        self.connect("chemicals.chemical_out", "dosing.chemical_in")
        self.connect("dosing.fluid_out", "hx.hot_in")
        self.connect("hx.hot_out", "heat_pump.source_in")
        self.connect("heat_pump.source_out", "injection.fluid_in")
        self.connect("injection.branch1_out", "d0.return_in")
        self.connect("injection.branch2_out", "d1.return_in")
        self.connect("grid.power_out", "d0.power_in")
        self.connect("grid.power_out", "d1.power_in")
        self.connect("grid.power_out", "heat_pump.power_in")
        self.connect("grid.power_out", "chiller.power_in")
        self.connect("grid.power_out", "chiller_cooler.power_in")
        self.connect("degasser.gas_out", "makeup.gas_in")
        self.connect("gas_grid.gas_out", "makeup.grid_in")
        self.connect("makeup.fuel_out", "boiler.fuel_in")
        self.connect("makeup.excess_out", "flare.gas_in")
        self.connect("heat_users.return_out", "hx.cold_in")
        self.connect("hx.cold_out", "heat_pump.sink_in")
        self.connect("heat_pump.sink_out", "boiler.fluid_in")
        self.connect("boiler.fluid_out", "loads.fluid_in")
        self.connect("loads.branch1_out", "heat_return.branch1_in")
        self.connect("loads.branch2_out", "chiller.generator_in")
        self.connect("chiller.generator_out", "heat_return.branch2_in")
        self.connect("heat_return.fluid_out", "heat_users.supply_in")
        self.connect("cool_users.return_out", "chiller.chilled_in")
        self.connect("chiller.chilled_out", "cool_users.supply_in")
        self.connect("chiller.cooling_out", "chiller_cooler.fluid_in")
        self.connect("chiller_cooler.fluid_out", "chiller.cooling_in")
        self.connect("boiler.flue_out", "air.gas_in")
        self.connect("flare.flue_out", "air.gas_in")
        self.connect("flare.loss_out", "air.heat_in")
        self.connect("boiler.loss_out", "air.heat_in")
        self.connect("air.air_out", "chiller_cooler.air_in")
        self.connect("chiller_cooler.air_out", "air.air_in")
