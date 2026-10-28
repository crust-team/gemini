"""Public composable equipment and plant API."""

from .container import ModuleDict, ModuleList, Sequential
from .heat import Boiler, HeatExchanger
from .module import Module, no_outputs
from .pumps import ESP, BoosterPump, InjectionPump
from .subsurface import InjectionReservoir, InjectionWell, ProductionReservoir, ProductionWell
from .treatment import Blowdown, Degasser, Filter

__all__ = [
    "Module",
    "no_outputs",
    "Sequential",
    "ModuleList",
    "ModuleDict",
    "Boiler",
    "HeatExchanger",
    "ESP",
    "BoosterPump",
    "InjectionPump",
    "InjectionReservoir",
    "InjectionWell",
    "ProductionReservoir",
    "ProductionWell",
    "Blowdown",
    "Degasser",
    "Filter",
]

from .balance import collect_flows, energy_balance, mass_balance
from .catalogue import create, get, list_modules
from .wiring import trace_wiring

list = list_modules

__all__ += [
    "collect_flows",
    "energy_balance",
    "mass_balance",
    "trace_wiring",
    "create",
    "get",
    "list",
]
