"""The plants that ship as spec files in ``specs/``, registered under their file names."""

from functools import partial
from pathlib import Path

from gemini.core.modules import registry
from gemini.core.modules.plants import reader
from gemini.core.modules.plants.builder import Plant
from gemini.core.modules.serialization import Report
from gemini.utils.files import read_json

SPECS = Path(__file__).parent / "specs"


def shipped(name):
    """Return the spec file of the shipped plant ``name`` as a dictionary."""
    return read_json(SPECS / f"{name}.json")


def build(name):
    """Return a new plant built from the shipped spec ``name``."""
    return reader.read(Plant, shipped(name))


def fill(plant, name):
    """Add the modules, wiring and outputs of the shipped spec ``name`` to an empty ``plant``."""
    reader.populate(plant, shipped(name), Report(strict=True))


def register_shipped():
    """Register every shipped spec as a plant under its file name."""
    for path in sorted(SPECS.glob("*.json")):
        registry.register_plant(path.stem, partial(build, path.stem))


def has(name):
    """Return whether a spec file ships for ``name``."""
    return (SPECS / f"{name}.json").exists()
