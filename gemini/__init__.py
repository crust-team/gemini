"""GEMINI: load a plant, choose a dataset, and simulate, replay or run live."""

from gemini import analysis, checks, economics, errors, optim, profiles, testing
from gemini.analysis.kpi import kpi
from gemini.core import legacy, modules, runtime
from gemini.core.data.dataset import Dataset
from gemini.core.engine.clock import Clock
from gemini.core.engine.engine import Engine
from gemini.core.engine.evaluate import evaluate
from gemini.core.engine.results import Results
from gemini.core.modules import plants
from gemini.core.modules.module import no_outputs
from gemini.core.modules.plants import Plant
from gemini.core.physics import units
from gemini.core.types import BRINE, WATER, Fluid, Ports, Profile, Quantity, Stream, streams

__version__ = "1.0.3"
API_VERSION = 1
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
