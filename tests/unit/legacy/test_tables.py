"""Legacy conversion table smoke tests."""

from gemini.legacy import tables


def test_tables_are_centralised():
    """Known old node/property names map in the legacy package only."""
    assert tables.TYPES["heat_exchanger"] == "heat_exchanger"
    assert tables.PORTS["esp"]["out"] == "discharge"
    assert tables.NODE_PATHS["esp_1ee3"] == "doublet.esp"
