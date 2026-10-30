"""Convert an old GEMINI project folder into a plant spec."""

from gemini.core.modules.plants.catalogue import get


def convert_legacy(folder):
    """Return the format 2 spec of the old GEMINI project in ``folder``.

    The folder holds what the old application saved: ``diagram.json`` (the nodes and links),
    one ``<node>_<id>.param`` file per diagram node with its properties, dated values and tag
    names, and any other file (the data CSV, ``well_trajectory.csv``, ``plant.conf``), which is
    read as-is and not converted. The bridge maps the example project's ten nodes
    (``gemini.core.legacy.tables.NODE_PATHS``): another node set, a missing ``.param`` file or an
    unit it does not know raises ``LegacyFormatError``. Old fields that have no new counterpart are
    listed in one ``GeminiWarning``. The data CSV is converted separately with
    ``gm.legacy.to_dataset``.

    The result is ``DoubletHeatPlant`` filled with the converted SI parameters, dated histories,
    fluids, bindings and assumptions, as ``plant.to_spec()`` writes them. ``core.legacy`` sits
    above this package in the import order, so it is imported inside the function.
    """
    from gemini.core.legacy import read_project, to_plant

    project = read_project(folder)
    return to_plant(project, get("DoubletHeatPlant")).to_spec()
