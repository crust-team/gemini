"""GEMINI: a general geothermal heating and cooling package."""

from gemini import (
    analysis,
    compiler,
    data,
    errors,
    evaluate,
    modules,
    ops,
    optim,
    physics,
    plants,
    runtime,
    units,
)
from gemini._utils.version import package_version
from gemini.engine.engine import Engine
from gemini.modules import Inlet, Module, Outlet, Output, Parameter
from gemini.plants import Plant
from gemini.run import (
    Assumptions,
    Constraint,
    Dataset,
    Problem,
    Results,
    call,
    live,
    replay,
    resume,
    schedule,
    simulate,
)
from gemini.types import BRINE, WATER, Fluid, Stream

__version__ = package_version()
__all__ = [
    "Module",
    "Plant",
    "Parameter",
    "Inlet",
    "Outlet",
    "Output",
    "Stream",
    "Fluid",
    "BRINE",
    "WATER",
    "Problem",
    "Constraint",
    "Assumptions",
    "schedule",
    "simulate",
    "replay",
    "live",
    "resume",
    "call",
    "Results",
    "Dataset",
    "Engine",
    "modules",
    "plants",
    "physics",
    "ops",
    "runtime",
    "units",
    "errors",
    "data",
    "optim",
    "evaluate",
    "analysis",
    "compiler",
]


def __dir__():
    """Expose only the documented API in interactive completion."""
    return sorted(__all__)
