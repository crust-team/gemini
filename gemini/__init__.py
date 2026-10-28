"""GEMINI: load a plant, choose a dataset, and simulate, replay or run live."""

from gemini import legacy, optim
from gemini.core import modules, runtime
from gemini.core.data.dataset import Dataset
from gemini.core.engine.clock import Clock
from gemini.core.engine.engine import Engine
from gemini.core.modules import plants
from gemini.core.modules.module import no_outputs
from gemini.core.physics import units
from gemini.core.types import BRINE, WATER, Fluid, Ports, Profile, Quantity, Stream

__version__ = "1.0.3"
__all__ = [
    "Engine",
    "Clock",
    "Dataset",
    "Profile",
    "Stream",
    "Ports",
    "Fluid",
    "BRINE",
    "WATER",
    "Quantity",
    "runtime",
    "units",
    "modules",
    "plants",
    "legacy",
    "optim",
    "no_outputs",
    "__version__",
]


def __dir__():
    """Expose only the documented API in interactive completion."""
    return sorted(__all__)
