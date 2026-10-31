"""Views of a plant's wiring."""

import gemini as gm
from gemini.modules.plants._utils import listing


def test_summary_counts_parameters_of_a_nested_plant():
    """A nested plant counts the parameters of all its modules."""
    plant = gm.Plant("Counts")
    plant.add("Doublet", "doublet")
    rows = listing.summary(plant).splitlines()
    assert rows[-1] == f"Total parameters: {len(list(plant.parameters()))}"
    assert rows[2].split()[:3] == ["doublet", "Doublet", "plants"]


def test_connection_list_is_empty_without_connections():
    """No connections, no rows."""
    assert listing.connection_list(gm.Plant("Empty")) == []
