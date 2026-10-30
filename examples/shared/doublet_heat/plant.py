"""Transitional ``DoubletHeatPlant``: a ``Plant`` that builds the shipped spec of that name.

``DoubletHeatPlant()`` and ``DoubletHeatPlant.load(path)`` keep working for the stored plant file
while the plant moves to ``gm.plants``; the wiring lives in the spec file, not in this class.
"""

from gemini.core.modules.plants import Plant, library


class DoubletHeatPlant(Plant):
    """Doublet, degasser, filters, heat exchanger and injection pump built from their spec."""

    def __init__(self):
        """Add the modules, wiring and outputs of the shipped spec."""
        super().__init__("DoubletHeatPlant")
        library.fill(self, "DoubletHeatPlant")
