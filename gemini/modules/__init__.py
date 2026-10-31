"""Public composable equipment and plant API."""

from ._utils import registry
from ._utils.balance import collect_flows, emissions, energy_balance, mass_balance
from ._utils.container import ModuleDict, ModuleList
from ._utils.registry import categories, get, load_file, names, register
from ._utils.wiring import trace_wiring
from .control import PIDController
from .cooling import AbsorptionUnit, AdsorptionChiller
from .demand import CoolingConsumer, HeatConsumer
from .exchangers import Cooler, HeatExchanger
from .heating import CHP, Boiler, ElectricBoiler, HeatPump
from .module import Module
from .piping import GasGrid, GasMakeup, Mixer, Pipe, PressurizationTank, Splitter, Valve
from .plants import ATESPlant, CoolingSubstation, HeatingSubstation
from .power import ORC, FlashTurbine, GridConnection, Separator
from .pumps import ESP, CentrifugalPump, GasCompressor, InjectionPump, LineShaftPump
from .storage import AquiferStorage, IceStorage, ThermalStorage
from .subsurface import (
    BoreholeField,
    DownholeHeatExchanger,
    InjectionReservoir,
    ProductionReservoir,
    ThermalDecline,
)
from .treatment import Blowdown, Degasser, Desander, Filter, Flare, InhibitorDosing, Vent
from .wells import InjectionWell, ProductionWell

__all__ = [
    "Module",
    "ModuleList",
    "ModuleDict",
    "Boiler",
    "ElectricBoiler",
    "Flare",
    "GasGrid",
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
    "HeatingSubstation",
    "CoolingSubstation",
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
