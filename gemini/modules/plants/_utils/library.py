"""The plants that ship as structure files in ``gemini/assets/plants/``, under their file names."""

from gemini.modules._utils.serialization import Report
from gemini.modules.plant import Plant
from gemini.modules.plants._utils import reader
from gemini.utils.files import read_json
from gemini.utils.paths import ASSET_PLANTS


def shipped(name):
    """Return the spec file of the shipped plant ``name`` as a dictionary."""
    return read_json(ASSET_PLANTS / f"{name}.json")


def build(name):
    """Return a new plant built from the shipped spec ``name``."""
    return reader.read(Plant, shipped(name))


def fill(plant, name):
    """Add the modules, wiring and outputs of the shipped spec ``name`` to an empty ``plant``."""
    reader.populate(plant, shipped(name), Report(strict=True))


def has(name):
    """Return whether a spec file ships for ``name``."""
    return (ASSET_PLANTS / f"{name}.json").exists()
