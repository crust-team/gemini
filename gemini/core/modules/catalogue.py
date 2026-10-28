"""Class-creation registry for built-in and user modules."""

from gemini.core.modules.module import MODULE_REGISTRY, Module
from gemini.core.types.fluid import Fluid


def list_modules():
    """Return registered names grouped by derived category."""
    grouped = {}
    for name, cls in sorted(MODULE_REGISTRY.items()):
        if cls.category == "user":
            continue
        grouped.setdefault(cls.category, []).append(name)
    return grouped


def get(name: str) -> type[Module]:
    """Resolve a derived module name."""
    try:
        return MODULE_REGISTRY[name]
    except KeyError as exc:
        raise ValueError(f"Unknown module {name!r}") from exc


def create(name: str, params=None, *, fluid: Fluid | None = None) -> Module:
    """Construct a module and fill keyword parameter values."""
    values = dict(params or {})
    if fluid is not None:
        values["fluid"] = fluid
    return get(name)(**values)
