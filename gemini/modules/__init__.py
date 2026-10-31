"""Public composable equipment and plant API."""

from ._utils import registry
from ._utils.balance import collect_flows, emissions, energy_balance, mass_balance
from ._utils.registry import categories, get, load_file, names, register
from ._utils.wiring import trace_wiring
from .container import ModuleDict, ModuleList
from .control import PIDController
from .cooling import AbsorptionUnit, AdsorptionChiller
from .environment import Atmosphere, Formation
from .exchangers import Cooler, HeatExchanger
from .grids import ChemicalGrid, CoolingGrid, ElectricityGrid, GasGrid, HeatingGrid, WasteGrid
from .heating import CHP, Boiler, ElectricBoiler, HeatPump
from .module import Module
from .piping import GasMakeup, Mixer, Pipe, PressurizationTank, Splitter, Valve
from .plants import (
    ATESPlant,
    CoolingSubstation,
    DistrictNetwork,
    Doublet,
    DoubletHeatPlant,
    HackathonPlant,
    HeatingSubstation,
    MultiWellPlant,
)
from .plants.boilerchpplant import BoilerChpPlant
from .plants.districtenergyplant import DistrictEnergyPlant
from .plants.nodaldoublet import NodalDoublet
from .plants.parallelexchangerplant import ParallelExchangerPlant
from .power import ORC, FlashTurbine, Separator
from .pumps import (
    ESP,
    CentrifugalPump,
    CirculationPump,
    GasCompressor,
    InjectionPump,
    LineShaftPump,
)
from .storage import AquiferStorage, IceStorage, ThermalStorage
from .subsurface import (
    BoreholeField,
    DownholeHeatExchanger,
    InjectionReservoir,
    ProductionReservoir,
    ThermalDecline,
)
from .treatment import Blowdown, Degasser, Desander, Filter, Flare, InhibitorDosing
from .wells import InjectionWell, ProductionWell

__all__ = [
    "Module",
    "ModuleList",
    "ModuleDict",
    "Boiler",
    "ElectricBoiler",
    "Flare",
    "GasGrid",
    "Atmosphere",
    "Formation",
    "ElectricityGrid",
    "HeatingGrid",
    "CoolingGrid",
    "WasteGrid",
    "ChemicalGrid",
    "GasMakeup",
    "HeatExchanger",
    "HeatPump",
    "AbsorptionUnit",
    "AdsorptionChiller",
    "CHP",
    "Cooler",
    "ESP",
    "InjectionPump",
    "CentrifugalPump",
    "CirculationPump",
    "LineShaftPump",
    "GasCompressor",
    "InjectionReservoir",
    "InjectionWell",
    "ProductionReservoir",
    "ProductionWell",
    "ThermalDecline",
    "AquiferStorage",
    "BoreholeField",
    "DownholeHeatExchanger",
    "Blowdown",
    "Degasser",
    "Filter",
    "Desander",
    "InhibitorDosing",
    "Mixer",
    "Pipe",
    "PressurizationTank",
    "Splitter",
    "Valve",
    "ThermalStorage",
    "IceStorage",
    "PIDController",
    "ORC",
    "Separator",
    "FlashTurbine",
    "HeatingSubstation",
    "CoolingSubstation",
    "ATESPlant",
    "NodalDoublet",
    "ParallelExchangerPlant",
    "BoilerChpPlant",
    "DistrictEnergyPlant",
    "Doublet",
    "DoubletHeatPlant",
    "DistrictNetwork",
    "MultiWellPlant",
    "HackathonPlant",
    "collect_flows",
    "emissions",
    "energy_balance",
    "mass_balance",
    "trace_wiring",
    "names",
    "get",
    "categories",
    "register",
    "load_file",
]

for _value in map(globals().get, __all__):
    if isinstance(_value, type) and issubclass(_value, Module) and _value.category is not None:
        registry.register(_value)
