"""GEMINI: load a plant, choose a dataset, and simulate, replay or run live."""

from gemini import analysis, checks, economics, errors, modules, optim, profiles, testing
from gemini.analysis.kpi import kpi
from gemini.backends import runtime
from gemini.engine.clock import Clock
from gemini.engine.engine import Engine
from gemini.engine.evaluate import evaluate
from gemini.engine.results import Results
from gemini.modules import plants
from gemini.modules.module import no_outputs
from gemini.modules.plants import Plant
from gemini.physics import units
from gemini.types import BRINE, WATER, Fluid, Ports, Profile, Quantity, Stream, streams
from gemini.utils import legacy
from gemini.utils.data.dataset import Dataset

__version__ = "1.0.3"
API_VERSION = 2
__all__ = [
    "Engine",
    "Plant",
    "Results",
    "evaluate",
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
    "streams",
    "modules",
    "plants",
    "profiles",
    "analysis",
    "economics",
    "kpi",
    "checks",
    "testing",
    "legacy",
    "optim",
    "errors",
    "no_outputs",
    "__version__",
    "API_VERSION",
]


def __dir__():
    """Expose only the documented API in interactive completion."""
    return sorted(__all__)
