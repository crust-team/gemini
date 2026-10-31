"""The measured doublet and its surface equipment: filters, degasser, exchanger, pump."""

from gemini.modules.container import ModuleDict
from gemini.modules.declarations import Inlet, Outlet
from gemini.modules.exchangers import HeatExchanger
from gemini.modules.pumps import InjectionPump
from gemini.modules.treatment import Degasser, Filter
from gemini.plants.doublet import Doublet
from gemini.plants.plant import Plant
from gemini.types import Power, Stream


class DoubletHeatPlant(Plant):
    """The measured doublet and its surface equipment: filters, degasser, exchanger, pump."""

    def __init__(self):
        """Declare the modules, ports and connections."""
        super().__init__()

        # Modules
        self.doublet = Doublet()
        self.degasser = Degasser()
        self.filters = ModuleDict({"hot": Filter(), "cold": Filter()})
        self.heat_exchanger = HeatExchanger()
        self.injection_pump = InjectionPump()

        # Inlets
        self.return_in = Inlet(Stream)
        self.power_in = Inlet(Power, kind="electricity")

        # Outlets
        self.supply_out = Outlet(Stream)
        self.gas_out = Outlet(Stream, kind="gas")

        # Connections
        self.connect("return_in", "heat_exchanger.cold_in")
        self.connect("power_in", "doublet.power_in")
        self.connect("power_in", "injection_pump.power_in")
        self.connect("doublet.supply_out", "degasser.fluid_in")
        self.connect("degasser.liquid_out", "filters.hot.fluid_in")
        self.connect("filters.hot.fluid_out", "heat_exchanger.hot_in")
        self.connect("heat_exchanger.hot_out", "filters.cold.fluid_in")
        self.connect("filters.cold.fluid_out", "injection_pump.fluid_in")
        self.connect("injection_pump.fluid_out", "doublet.return_in")
        self.connect("heat_exchanger.cold_out", "supply_out")
        self.connect("degasser.gas_out", "gas_out")
