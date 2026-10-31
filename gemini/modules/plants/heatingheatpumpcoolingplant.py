"""Heat pump heating with a peak boiler, and a compression chiller."""

from gemini.modules.container import ModuleDict
from gemini.modules.environment import Atmosphere
from gemini.modules.exchangers import Cooler, HeatExchanger
from gemini.modules.grids import CoolingGrid, ElectricityGrid, GasGrid, HeatingGrid
from gemini.modules.heating import Boiler, HeatPump
from gemini.modules.piping import GasMakeup, Pipe
from gemini.modules.plant import Plant
from gemini.modules.plants.doublet import Doublet
from gemini.modules.pumps import InjectionPump
from gemini.modules.treatment import Degasser, Filter, Flare


class HeatingHeatPumpCoolingPlant(Plant):
    """Heat pump heating with a peak boiler, and a compression chiller."""

    purpose = "both"

    def __init__(self):
        """Declare the modules, ports and connections."""
        super().__init__()

        # Modules
        self.doublet = Doublet()
        self.degasser = Degasser()
        self.filters = ModuleDict({"hot": Filter(), "cold": Filter()})
        self.heat_exchanger = HeatExchanger()
        self.heat_pump = HeatPump()
        self.injection_pump = InjectionPump()
        self.heating_return_pipe = Pipe()
        self.peak_boiler = Boiler()
        self.heating_supply_pipe = Pipe()
        self.heating_consumer = HeatingGrid()
        self.cooling_return_pipe = Pipe()
        self.compression_chiller = HeatPump()
        self.cooling_supply_pipe = Pipe()
        self.cooling_consumer = CoolingGrid()
        self.gas_grid = GasGrid()
        self.electricity_grid = ElectricityGrid()
        self.gas_makeup = GasMakeup()
        self.flare = Flare()
        self.atmosphere = Atmosphere()
        self.compression_cooler = Cooler()

        # Connections
        self.connect("degasser.gas_out", "gas_makeup.gas_in")
        self.connect("gas_grid.gas_out", "gas_makeup.grid_in")
        self.connect("gas_makeup.fuel_out", "peak_boiler.fuel_in")
        self.connect("gas_makeup.excess_out", "flare.gas_in")
        self.connect("doublet.supply_out", "degasser.fluid_in")
        self.connect("degasser.liquid_out", "filters.hot.fluid_in")
        self.connect("filters.hot.fluid_out", "heat_exchanger.hot_in")
        self.connect("heat_exchanger.hot_out", "heat_pump.source_in")
        self.connect("heat_pump.source_out", "filters.cold.fluid_in")
        self.connect("filters.cold.fluid_out", "injection_pump.fluid_in")
        self.connect("injection_pump.fluid_out", "doublet.return_in")
        self.connect("heating_return_pipe.fluid_out", "heat_exchanger.cold_in")
        self.connect("heat_exchanger.cold_out", "heat_pump.sink_in")
        self.connect("heat_pump.sink_out", "peak_boiler.fluid_in")
        self.connect("heating_supply_pipe.fluid_out", "heating_consumer.supply_in")
        self.connect("compression_chiller.source_out", "cooling_supply_pipe.fluid_in")
        self.connect("cooling_supply_pipe.fluid_out", "cooling_consumer.supply_in")
        self.connect("electricity_grid.power_out", "doublet.power_in")
        self.connect("electricity_grid.power_out", "heat_pump.power_in")
        self.connect("electricity_grid.power_out", "injection_pump.power_in")
        self.connect("electricity_grid.power_out", "compression_chiller.power_in")
        self.connect("heating_consumer.return_out", "heating_return_pipe.fluid_in")
        self.connect("cooling_consumer.return_out", "cooling_return_pipe.fluid_in")
        self.connect("atmosphere.air_out", "heating_return_pipe.air_in")
        self.connect("atmosphere.air_out", "heating_supply_pipe.air_in")
        self.connect("atmosphere.air_out", "cooling_return_pipe.air_in")
        self.connect("atmosphere.air_out", "cooling_supply_pipe.air_in")
        self.connect("peak_boiler.flue_out", "atmosphere.gas_in")
        self.connect("flare.flue_out", "atmosphere.gas_in")
        self.connect("flare.loss_out", "atmosphere.heat_in")
        self.connect("compression_chiller.sink_out", "compression_cooler.fluid_in")
        self.connect("compression_cooler.fluid_out", "compression_chiller.sink_in")
        self.connect("atmosphere.air_out", "compression_cooler.air_in")
        self.connect("compression_cooler.air_out", "atmosphere.air_in")
        self.connect("electricity_grid.power_out", "compression_cooler.power_in")
        self.connect("heating_return_pipe.loss_out", "atmosphere.heat_in")
        self.connect("heating_supply_pipe.loss_out", "atmosphere.heat_in")
        self.connect("cooling_return_pipe.loss_out", "atmosphere.heat_in")
        self.connect("cooling_supply_pipe.loss_out", "atmosphere.heat_in")
        self.connect("peak_boiler.loss_out", "atmosphere.heat_in")
        self.connect("peak_boiler.fluid_out", "heating_supply_pipe.fluid_in")
        self.connect("cooling_return_pipe.fluid_out", "compression_chiller.source_in")
