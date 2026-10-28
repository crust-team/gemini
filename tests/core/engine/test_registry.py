"""Component discovery, identity and metadata contracts."""

import inspect
import json
from pathlib import Path

import pytest

from gemini.core.engine import registry


def test_every_component_module_is_discovered():
    """Every equipment file contributes concrete components with unique serialisable schemas."""
    schemas = registry.list_components()
    names = [s["name"] for s in schemas]
    assert len(names) == len(set(names))
    modules = {registry.get_component(name).__module__ for name in names}
    root = Path(__file__).parents[3] / "gemini/components"
    expected = {
        "gemini.components." + ".".join(p.relative_to(root).with_suffix("").parts)
        for p in root.rglob("*.py")
        if p.name != "__init__.py"
    }
    assert modules == expected
    for schema in schemas:
        json.dumps(schema)
        cls = registry.get_component(schema["name"])
        assert not inspect.isabstract(cls)
        for model in (cls.Params, cls.Inputs, cls.Outputs):
            for field in model.model_fields.values():
                assert field.description and "[" in field.description and "]" in field.description
    with pytest.raises(ValueError, match="Unknown component"):
        registry.create("missing", {})


def test_duplicate_names_are_rejected(monkeypatch):
    """Discovery catches two distinct classes claiming the same public component name."""
    real = registry.inspect.getmembers

    def members(module, predicate):
        result = real(module, predicate)
        concrete = [
            (n, c)
            for n, c in result
            if getattr(c, "name", None) == "esp" and c.__module__ == module.__name__
        ]
        return result + concrete

    monkeypatch.setattr(registry.inspect, "getmembers", members)
    with pytest.raises(ValueError, match="Duplicate component name"):
        registry._discover()
