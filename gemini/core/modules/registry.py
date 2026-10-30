"""The one registry of module and plant types: stable names, categories and how to get each.

A module class registers under its class name and its ``category``. A plant that exists as a spec
registers under its name with a ``build`` function that returns a new plant. Both kinds share one
table, so a plant spec can name any of them as the ``type`` of a child.
"""

from dataclasses import dataclass
from typing import Any

from gemini.core.modules.module import Module
from gemini.errors import NotImplementedYet, UnknownNameError, ValidationError
from gemini.utils.strings import close_matches, did_you_mean, join_names

CATEGORIES = (
    "subsurface",
    "well",
    "pump",
    "separation",
    "heat_exchange",
    "heat_pump",
    "chiller",
    "boiler",
    "storage",
    "network",
    "consumer",
    "plant",
)
"""Every module category, in display order."""


@dataclass(frozen=True)
class _Entry:
    """One registered type: a module class, or the function that builds a spec plant."""

    category: str
    module: type[Module] | None = None
    build: Any = None


_entries = {}


def _check_category(name, category):
    if category not in CATEGORIES:
        raise ValidationError(
            f"modules.register: {name}.category = {category!r}; expected one of "
            f"{join_names(CATEGORIES)}{did_you_mean(category, CATEGORIES)}",
            path=name,
            suggestions=close_matches(category, CATEGORIES),
        )


def register(cls):
    """Add a ``Module`` class under its class name and return it, so it can join a plant.

    Registering the same class again does nothing; another class of that name is refused.
    """
    if not (isinstance(cls, type) and issubclass(cls, Module)):
        raise ValidationError(f"modules.register: cls = {cls!r}; expected a Module class")
    name = cls.__name__
    _check_category(name, cls.category)
    existing = _entries.get(name)
    if existing is not None and existing.module is not cls:
        raise ValidationError(f"modules.register: name {name!r} is already taken", path=name)
    _entries[name] = _Entry(cls.category, module=cls)
    return cls


def register_plant(name, build):
    """Add a spec plant under ``name``; ``build()`` returns a new plant without values."""
    if name in _entries:
        raise ValidationError(f"plants.register: name {name!r} is already taken", path=name)
    _entries[name] = _Entry("plant", build=build)


def names(category=None):
    """Return the registered names, sorted, of every category or of one."""
    if category is not None:
        _check_category("names", category)
    return sorted(name for name, entry in _entries.items() if category in (None, entry.category))


def categories():
    """Return the fixed category list."""
    return list(CATEGORIES)


def category(name):
    """Return the category of a registered name."""
    return _entry(name).category


def _entry(name):
    entry = _entries.get(name)
    if entry is None:
        raise UnknownNameError(
            f"modules: unknown module type {name!r}{did_you_mean(name, _entries)}",
            path=name,
            suggestions=close_matches(name, _entries),
        )
    return entry


def get(name):
    """Return the class registered as ``name``, or a new plant for a spec plant.

    Both answer ``describe()``, ``parameter_schema()`` and ``validate_params(params)``.
    """
    entry = _entry(name)
    return entry.module if entry.module is not None else entry.build()


def load_file(path):
    """Import the Python file at ``path`` and register the ``Module`` classes it defines."""
    raise NotImplementedYet(f"modules.load_file: path = {path!r}; lands in this step")
