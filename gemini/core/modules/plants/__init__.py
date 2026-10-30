"""Plants built from data, with their spec functions, and the handwritten special cases."""

from .atesplant import ATESPlant
from .builder import Plant
from .coolingsubstation import CoolingSubstation
from .districtnetwork import DistrictNetwork
from .doublet import Doublet
from .heatingsubstation import HeatingSubstation
from .library import register_shipped
from .migration import migrate
from .multiwellplant import MultiWellPlant
from .schema import spec_schema
from .spec import from_dict, from_spec, validate

__all__ = [
    "Plant",
    "from_spec",
    "from_dict",
    "validate",
    "spec_schema",
    "migrate",
    "Doublet",
    "MultiWellPlant",
    "HeatingSubstation",
    "CoolingSubstation",
    "DistrictNetwork",
    "ATESPlant",
]

register_shipped()
