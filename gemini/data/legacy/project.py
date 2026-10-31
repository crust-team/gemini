"""Read an old GEMINI project folder into a plant."""

from gemini.data.legacy.convert import to_plant
from gemini.data.legacy.files import GeminiProject
from gemini.plants._utils.catalogue import get


def from_folder(folder):
    """Return the plant of the old GEMINI project in ``folder``, ``gm.Plant.from_legacy``.

    The bridge maps the example project's ten nodes (``gemini.data.legacy.tables.NODE_PATHS``):
    another node set, a missing ``.param`` file or a unit it does not know raises
    ``ValidationError``. Old fields that have no new counterpart are listed in one
    ``GeminiWarning``. The data CSV is converted separately, by the internal
    ``gemini.data.legacy.to_dataset``.

    The result is ``DoubletHeatPlant`` filled with the converted SI parameters, dated histories,
    fluids, bindings and assumptions.
    """
    return to_plant(GeminiProject.from_folder(folder), get("DoubletHeatPlant"))
