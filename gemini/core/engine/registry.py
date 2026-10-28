"""Discover equipment components without a manual component catalogue."""

import importlib
import inspect
import pkgutil

from gemini.core.modules.module import Module


def _discover() -> dict[str, type[Module]]:
    package = importlib.import_module("gemini.core.modules")
    discovered = {}
    for info in pkgutil.walk_packages(package.__path__, package.__name__ + "."):
        module = importlib.import_module(info.name)
        for _, cls in inspect.getmembers(module, inspect.isclass):
            if (
                not issubclass(cls, Module)
                or inspect.isabstract(cls)
                or cls.category == "plant"
                or cls.__module__ != module.__name__
            ):
                continue
            if cls.name in discovered:
                raise ValueError(f"Duplicate component name {cls.name!r}")
            discovered[cls.name] = cls
    return discovered


_MODULES = _discover()


def list_modules() -> list[dict]:
    """Return deterministic JSON-serialisable equipment schemas."""
    return [_MODULES[name].schema() for name in sorted(_MODULES)]


def get(name: str) -> type[Module]:
    """Resolve a component name or raise a clear configuration error."""
    try:
        return _MODULES[name]
    except KeyError as exc:
        raise ValueError(f"Unknown component {name!r}") from exc


def create(name: str, params: dict, *, fluid: str = "brine") -> Module:
    """Construct a validated component with SI parameters and a named fluid model."""
    return get(name)(params, fluid=fluid)
