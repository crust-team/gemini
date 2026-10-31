"""The plants that ship as structure files in ``gemini/assets/plants/``, under their file names."""

from functools import partial

from gemini.modules._utils import registry
from gemini.modules._utils.serialization import Report
from gemini.modules.plant import Plant
from gemini.modules.plants import reader
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


def register_shipped(classes):
    """Register every shipped spec as a plant under its file name.

    ``classes`` maps a name to the ``Plant`` subclass that builds that spec itself.
    """
    for path in sorted(ASSET_PLANTS.glob("*.json")):
        registry.register_plant(path.stem, classes.get(path.stem, partial(build, path.stem)))


def has(name):
    """Return whether a spec file ships for ``name``."""
    return (ASSET_PLANTS / f"{name}.json").exists()
