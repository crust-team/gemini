"""Discover equipment components without a manual component catalogue."""

import importlib
import inspect
import pkgutil

from gemini.core.base.component import Component


def _discover() -> dict[str, type[Component]]:
    package = importlib.import_module("gemini.components")
    discovered = {}
    for info in pkgutil.walk_packages(package.__path__, package.__name__ + "."):
        module = importlib.import_module(info.name)
        for _, cls in inspect.getmembers(module, inspect.isclass):
            if (
                not issubclass(cls, Component)
                or inspect.isabstract(cls)
                or cls.__module__ != module.__name__
            ):
                continue
            if cls.name in discovered:
                raise ValueError(f"Duplicate component name {cls.name!r}")
            discovered[cls.name] = cls
    return discovered


_COMPONENTS = _discover()


def list_components() -> list[dict]:
    """Return deterministic JSON-serialisable equipment schemas."""
    return [_COMPONENTS[name].schema() for name in sorted(_COMPONENTS)]


def get_component(name: str) -> type[Component]:
    """Resolve a component name or raise a clear configuration error."""
    try:
        return _COMPONENTS[name]
    except KeyError as exc:
        raise ValueError(f"Unknown component {name!r}") from exc


def create(name: str, params: dict, *, fluid: str = "brine") -> Component:
    """Construct a validated component with SI parameters and a named fluid model."""
    return get_component(name)(params, fluid=fluid)
