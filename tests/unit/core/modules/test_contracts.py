"""Declaration and forward conventions across every registered built-in module."""

import inspect

from gemini.core.modules.module import MODULE_REGISTRY


def test_every_forward_matches_its_declarations():
    """Every non-container built-in has exactly its declared forward arguments."""
    for cls in MODULE_REGISTRY.values():
        if cls.category in {"container", "user"}:
            continue
        module = cls()
        expected = set(module.inlets()) | set(module.controls()) | set(module.boundaries())
        actual = set(inspect.signature(module.forward).parameters)
        assert actual == expected, cls


def test_metadata_is_derived():
    """Names, descriptions and categories are derived at class creation."""
    heat_exchanger = MODULE_REGISTRY["heat_exchanger"]
    assert heat_exchanger.category == "heat"
    assert heat_exchanger.description.startswith("Two-stream heat exchanger")
    assert "name" not in heat_exchanger.__dict__ or heat_exchanger.name == "heat_exchanger"
