"""Declaration metadata across every registered built-in module."""

from gemini.core.modules.module import MODULE_REGISTRY


def test_metadata_is_derived():
    """Names, descriptions and categories are derived at class creation."""
    heat_exchanger = MODULE_REGISTRY["heat_exchanger"]
    assert heat_exchanger.category == "heat"
    assert heat_exchanger.description.startswith("Two-stream heat exchanger")
    assert "name" not in heat_exchanger.__dict__ or heat_exchanger.name == "heat_exchanger"
