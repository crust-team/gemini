"""Plants built from data, with their spec functions, and the handwritten special cases."""

from gemini.modules.plant import Plant

from ._utils.catalogue import example, get, names, templates
from ._utils.legacy_project import convert_legacy
from ._utils.migration import migrate
from ._utils.schema import spec_schema
from ._utils.spec import from_dict, from_spec, validate
from ._utils.templating import from_template
from .atesplant import ATESPlant
from .coolingsubstation import CoolingSubstation
from .districtnetwork import DistrictNetwork
from .doublet import Doublet
from .doubletheatplant import DoubletHeatPlant
from .hackathonplant import HackathonPlant
from .heatingsubstation import HeatingSubstation
from .multiwellplant import MultiWellPlant

__all__ = [
    "Plant",
    "from_spec",
    "from_dict",
    "validate",
    "spec_schema",
    "migrate",
    "names",
    "get",
    "example",
    "convert_legacy",
    "templates",
    "from_template",
    "HeatingSubstation",
    "CoolingSubstation",
    "ATESPlant",
    "Doublet",
    "DoubletHeatPlant",
    "DistrictNetwork",
    "MultiWellPlant",
    "HackathonPlant",
]
