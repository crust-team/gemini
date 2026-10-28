"""Declaration metadata and source conventions."""

import inspect

from gemini.core.modules.module import MODULE_REGISTRY

SECTIONS = [
    "# Modules",
    "# Parameters",
    "# Inlets",
    "# Controls",
    "# Boundaries",
    "# Outputs",
    "# Outlets",
]


def test_quantity_declarations_expose_units():
    """Annotated numeric declarations retain machine-readable units."""
    for cls in MODULE_REGISTRY.values():
        if cls.category in {"container", "user"}:
            continue
        module = cls()
        for declaration in module._declarations().values():
            schema = declaration.schema
            numeric = schema.get("type") in {"number", "integer"} or any(
                item.get("type") in {"number", "integer"} for item in schema.get("anyOf", [])
            )
            if numeric and declaration.kind not in {float, int}:
                assert declaration.unit is not None, (cls, declaration.name)


def test_init_section_comments_are_ordered():
    """Module declarations use fixed plain-text section comments in order."""
    for cls in MODULE_REGISTRY.values():
        if cls.category in {"container", "user"}:
            continue
        source = inspect.getsource(cls.__init__)
        positions = [source.find(section) for section in SECTIONS if section in source]
        assert positions == sorted(positions), cls
        assert not any(section + " -" in source for section in SECTIONS)
