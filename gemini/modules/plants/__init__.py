"""Plants built from data, with their spec functions, and the handwritten special cases."""

from gemini.modules.plant import Plant

from .atesplant import ATESPlant
from .catalogue import example, get, names, templates
from .coolingsubstation import CoolingSubstation
from .doublet import Doublet
from .heatingsubstation import HeatingSubstation
from .legacy_project import convert_legacy
from .library import register_shipped
from .migration import migrate
from .schema import spec_schema
from .spec import from_dict, from_spec, validate
from .templating import from_template

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
