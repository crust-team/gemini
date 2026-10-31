"""Convert an old GEMINI project folder into a plant dict."""

from gemini.plants._utils.catalogue import get


def convert_legacy(folder):
    """Return the plant dict of the old GEMINI project in ``folder``.

    The folder holds what the old application saved: ``diagram.json`` (the nodes and links),
    one ``<node>_<id>.param`` file per diagram node with its properties, dated values and tag
    names, and any other file (the data CSV, ``well_trajectory.csv``, ``plant.conf``), which is
    read as-is and not converted. The bridge maps the example project's ten nodes
    (``gemini.data.legacy.tables.NODE_PATHS``): another node set, a missing ``.param`` file or an
    unit it does not know raises ``ValidationError``. Old fields that have no new counterpart are
    listed in one ``GeminiWarning``. The data CSV is converted separately, by the
    internal ``gemini.data.legacy.to_dataset``.

    The result is ``DoubletHeatPlant`` filled with the converted SI parameters, dated histories,
    fluids, bindings and assumptions, as ``plant.to_dict()`` writes them. ``gemini.data.legacy``
    sits above this package in the import order, so it is imported inside the function.
    """
    from gemini.data.legacy import read_project, to_plant

    project = read_project(folder)
    return to_plant(project, get("DoubletHeatPlant")).to_dict()
