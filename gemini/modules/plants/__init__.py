"""Plants built from data, with their spec functions, and the handwritten special cases."""

from gemini.modules.plant import Plant

from ._utils.catalogue import example, get, names, templates
from ._utils.legacy_project import convert_legacy
from ._utils.library import register_shipped
from ._utils.migration import migrate
from ._utils.schema import spec_schema
from ._utils.spec import from_dict, from_spec, validate
from ._utils.templating import from_template
from .atesplant import ATESPlant
from .coolingsubstation import CoolingSubstation
from .doublet import Doublet
from .heatingsubstation import HeatingSubstation

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
]

register_shipped({"Doublet": Doublet})
