"""Declaration metadata and source conventions."""

import inspect

SECTIONS = [
    "# Modules",
    "# Parameters",
    "# Inlets",
    "# Controls",
    "# Boundaries",
    "# Outputs",
    "# Outlets",
]


def test_quantity_declarations_expose_units(module_class):
    """Annotated numeric declarations retain machine-readable units."""
    cls = module_class
    module = cls()
    for declaration in module._declarations().values():
        schema = declaration.schema
        numeric = schema.get("type") in {"number", "integer"} or any(
            item.get("type") in {"number", "integer"} for item in schema.get("anyOf", [])
        )
        if numeric and declaration.type not in {float, int}:
            assert declaration.unit is not None, (cls, declaration.name)


def test_init_section_comments_are_ordered(module_class):
    """Module declarations use fixed plain-text section comments in order."""
    cls = module_class
    source = inspect.getsource(cls.__init__)
    positions = [source.find(section) for section in SECTIONS if section in source]
    assert positions == sorted(positions), cls
    assert not any(section + " -" in source for section in SECTIONS)
