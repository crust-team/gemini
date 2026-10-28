"""GEMINI: load a plant, choose a dataset, and simulate, replay or run live."""

from gemini import optim
from gemini.core import modules
from gemini.core.config.io import load_plant
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
    "load_plant",
    "modules",
    "plants",
    "optim",
    "__version__",
]


def __dir__():
    """Expose only the documented API in interactive completion."""
    return sorted(__all__)
