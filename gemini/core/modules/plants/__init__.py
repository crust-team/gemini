"""Plants built from data, with their spec functions, and the handwritten special cases."""

from .atesplant import ATESPlant
from .builder import Plant
from .catalogue import get, names
from .coolingsubstation import CoolingSubstation
from .heatingsubstation import HeatingSubstation
from .library import register_shipped
from .migration import migrate
from .schema import spec_schema
from .spec import from_dict, from_spec, validate
from .templates import from_template

__all__ = [
    "Plant",
    "from_spec",
    "from_dict",
    "validate",
    "spec_schema",
    "migrate",
    "names",
    "get",
    "from_template",
    "HeatingSubstation",
    "CoolingSubstation",
    "ATESPlant",
]

register_shipped()
