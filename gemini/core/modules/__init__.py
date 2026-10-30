"""Public composable equipment and plant API."""

from . import registry
from .balance import collect_flows, emissions, energy_balance, mass_balance
from .container import ModuleDict, ModuleList
from .control import PIDController
from .demand import CoolingConsumer, HeatConsumer
from .heat import CHP, AbsorptionUnit, AdsorptionChiller, Boiler, Cooler, HeatExchanger, HeatPump
from .module import Module
from .piping import Mixer, Pipe, PressurizationTank, Splitter, Valve
from .plants import ATESPlant, CoolingSubstation, DistrictNetwork, HeatingSubstation, MultiWellPlant
from .power import ORC, FlashTurbine, GridConnection, Separator
from .pumps import ESP, CentrifugalPump, GasCompressor, InjectionPump, LineShaftPump
from .registry import categories, get, load_file, names, register
from .storage import IceStorage, ThermalStorage
from .subsurface import (
    AquiferStorage,
    BoreholeField,
    DownholeHeatExchanger,
    InjectionReservoir,
    InjectionWell,
    ProductionReservoir,
    ProductionWell,
    ThermalDecline,
)
from .treatment import Blowdown, Degasser, Desander, Filter, InhibitorDosing, Vent
from .wiring import trace_wiring

__all__ = [
    "Module",
    "ModuleList",
    "ModuleDict",
    "Boiler",
    "HeatExchanger",
    "HeatPump",
    "AbsorptionUnit",
    "AdsorptionChiller",
    "CHP",
    "Cooler",
    "ESP",
    "InjectionPump",
    "CentrifugalPump",
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
    "Vent",
    "HeatConsumer",
    "CoolingConsumer",
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
    "GridConnection",
    "MultiWellPlant",
    "HeatingSubstation",
    "CoolingSubstation",
    "DistrictNetwork",
    "ATESPlant",
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
