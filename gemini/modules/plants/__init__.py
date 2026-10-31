"""The plant classes and the functions of the plant dict."""

from gemini.modules.plant import Plant

from ._utils.catalogue import example, from_dict, get, names, validate
from ._utils.legacy_project import convert_legacy
from ._utils.schema import schema
from .atesplant import ATESPlant
from .coolingsubstation import CoolingSubstation
from .districtnetwork import DistrictNetwork
from .doublet import Doublet
from .doubletheatplant import DoubletHeatPlant
from .heatingabsorptioncoolingplant import HeatingAbsorptionCoolingPlant
from .heatingcoolingplant import HeatingCoolingPlant
from .heatingfullcoolingplant import HeatingFullCoolingPlant
from .heatingheatpumpcoolingplant import HeatingHeatPumpCoolingPlant
from .heatingplant import HeatingPlant
from .heatingsubstation import HeatingSubstation
from .multiwellplant import MultiWellPlant

__all__ = [
    "Plant",
    "from_dict",
    "validate",
    "schema",
    "names",
    "get",
    "example",
    "convert_legacy",
    "HeatingSubstation",
    "CoolingSubstation",
    "ATESPlant",
    "Doublet",
    "DoubletHeatPlant",
    "DistrictNetwork",
    "MultiWellPlant",
    "HeatingPlant",
    "HeatingCoolingPlant",
    "HeatingFullCoolingPlant",
    "HeatingAbsorptionCoolingPlant",
    "HeatingHeatPumpCoolingPlant",
]
