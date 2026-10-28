"""GEMINI: load a plant, choose a dataset, and simulate, replay or run live."""

from gemini import legacy, optim
from gemini.core import modules
from gemini.core.data.dataset import Dataset
from gemini.core.engine.clock import Clock
from gemini.core.engine.engine import Engine
from gemini.core.modules import plants
from gemini.core.types import BRINE, WATER, Fluid, Profile, Stream

__version__ = "1.0.3"
__all__ = [
    "Engine",
    "Clock",
    "Dataset",
    "Profile",
    "Stream",
    "Fluid",
    "BRINE",
    "WATER",
    "modules",
    "plants",
    "legacy",
    "optim",
    "__version__",
]


def __dir__():
    """Expose only the documented API in interactive completion."""
    return sorted(__all__)
