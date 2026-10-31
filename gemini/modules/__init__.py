"""Public composable equipment and module API."""

from gemini._utils.registry import categories, get, names

from ._utils.balance import collect_flows, emissions, energy_balance, mass_balance
from ._utils.wiring import trace_wiring
from .check import check
from .container import ModuleDict, ModuleList
from .control import PIDController
from .cooling import AbsorptionUnit, AdsorptionChiller
from .declarations import Boundary, Control, Inlet, Outlet, Output, Parameter, State
from .environment import Atmosphere, Formation
from .exchangers import Cooler, HeatExchanger
from .grids import ChemicalGrid, CoolingGrid, ElectricityGrid, GasGrid, HeatingGrid, WasteGrid
from .heating import CHP, Boiler, ElectricBoiler, HeatPump
from .module import Module, no_outputs
from .piping import GasMakeup, Mixer, Pipe, PressurizationTank, Splitter, Valve
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
    "collect_flows",
    "emissions",
    "energy_balance",
    "mass_balance",
    "trace_wiring",
    "names",
    "get",
    "categories",
    "check",
    "no_outputs",
    "Parameter",
    "Inlet",
    "Control",
    "Boundary",
    "State",
    "Output",
    "Outlet",
]
