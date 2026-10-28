"""Module discovery, identity and metadata contracts."""

import inspect
import json
from pathlib import Path

import pytest

from gemini.core.modules import catalogue as registry


def test_every_module_module_is_discovered():
    """Every equipment file contributes concrete modules with unique serialisable schemas."""
    schemas = registry.list_modules()
    names = [s["name"] for s in schemas]
    assert len(names) == len(set(names))
    modules = {registry.get(name).__module__ for name in names}
    root = Path(__file__).parents[4] / "gemini/core/modules"
    expected = {
        "gemini.core.modules." + ".".join(p.relative_to(root).with_suffix("").parts)
        for p in root.rglob("*.py")
        if p.name not in {"__init__.py", "module.py", "balance.py", "catalogue.py", "wiring.py"}
    }
    assert modules == expected
    for schema in schemas:
        json.dumps(schema)
        cls = registry.get(schema["name"])
        assert not inspect.isabstract(cls)
        for model in (cls.Params, cls.Inputs, cls.Outputs):
            for field in model.model_fields.values():
                assert field.description and "[" in field.description and "]" in field.description
    with pytest.raises(ValueError, match="Unknown module"):
        registry.create("missing", {})


def test_duplicate_names_are_rejected(monkeypatch):
    """Discovery catches two distinct classes claiming the same public module name."""
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
    with pytest.raises(ValueError, match="Duplicate module name"):
        registry._discover()
